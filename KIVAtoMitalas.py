# MODULES
import sys, getopt, os
import yaml
import math
from datetime import datetime
import pandas as pd, numpy as np

# GLOBALS
KIVAPATH = 'C:\\Program Files\\kiva-0.5.0-windows-64bit\\bin\\kiva.exe'

# Read the inputs
try:
   opts, args = getopt.getopt(sys.argv[1:],"hi:c:o:",["help","input=","climate=","output="])
except getopt.GetoptError:
   print('KIVAtoMitalas.py --input <INPUT_YML> --climate <EPW_FILE> --output <OUTPUT>')
   sys.exit(2)
for opt, arg in opts:
   if opt == '-h':
      print('KIVAtoMitalas.py --input <INPUT_YML> --climate <EPW_FILE> --output <OUTPUT>')
      sys.exit()
   elif opt in ("-i", "--input"):
      sInFile = arg
   elif opt in ("-c", "--climate"):
      sCliFile = arg
   elif opt in ("-o", "--output"):
      sOutFile = arg

# Process the climate data first
# Find the start of the records and load
iSkip=0
bHeaderFound = 0
with open(sCliFile) as f:
    for line in f:
        iSkip+=1
        if line[0:12] == 'DATA PERIODS':
            bHeaderFound=1
            break
if bHeaderFound == 0:
    print('Could not find start of climate data')
    sys.exit(2)
dfWeather = pd.read_csv(sCliFile, skiprows=iSkip, header=None)
# Slice out the drybuld temperatures and transfer dataframe to numpy
fDBtemps=dfWeather.loc[:,6].to_numpy()
iSamples = len(fDBtemps)
fourierTransform = np.fft.rfft(fDBtemps)
fourierTransform = fourierTransform/float(iSamples)
tempMagnitudes=abs(fourierTransform)
# Annual Temps data
fTmean = tempMagnitudes[0]
fTamp = tempMagnitudes[1]*2.0
fPhase = np.angle(fourierTransform[1])

# Load the YAML file
with open(sInFile, 'r') as stream:
    kiva_yml = yaml.safe_load(stream)

# Extract the interior air temperature (oC)
fBsmtTemp = kiva_yml['Boundaries']['Indoor Air Temperature']-273.15

# Extract height of wall above grade
fWallAboveGrade = kiva_yml['Foundation']['Wall']['Height Above Grade']

# Extract the perimeter coordinates and calculate the perimeter
fPerimCoord = kiva_yml['Foundation']['Polygon']
fPermLength = 0.0
for i in range(1, (len(fPerimCoord)-1), 1):
    j=i-1
    x1 = fPerimCoord[j][0]
    y1 = fPerimCoord[j][1]
    x2 = fPerimCoord[i][0]
    y2 = fPerimCoord[i][1]
    
    fPermLength+=math.sqrt(((x2-x1)**2)+((y2-y1)**2))

# Calculate the above-grade wall area
fAgArea = fWallAboveGrade*fPermLength

# Calulate the above-grade wall U-value
fRWall=0.0
# Start with wall itself
for layer in kiva_yml['Foundation']['Wall']['Layers']:
    # Pull material data
    fThisMatName = layer['Material']
    fThisCond = kiva_yml['Materials'][fThisMatName]['Conductivity']
    fRWall+=(layer['Thickness']/fThisCond)

# Now check the interior insulation
if 'Interior Vertical Insulation' in kiva_yml['Foundation']:
    # TODO: Check if kiva_yml['Foundation']['Interior Vertical Insulation']['Depth]> fWallAboveGrade
    fThisMatName = kiva_yml['Foundation']['Interior Vertical Insulation']['Material']
    fThisCond = kiva_yml['Materials'][fThisMatName]['Conductivity']
    fRWall+=(kiva_yml['Foundation']['Interior Vertical Insulation']['Thickness']/fThisCond)

# Now check the exterior insulation
if 'Exterior Vertical Insulation' in kiva_yml['Foundation']:
    # TODO: Check if kiva_yml['Foundation']['Exterior Vertical Insulation']['Depth]> fWallAboveGrade
    fThisMatName = kiva_yml['Foundation']['Exterior Vertical Insulation']['Material']
    fThisCond = kiva_yml['Materials'][fThisMatName]['Conductivity']
    fRWall+=(kiva_yml['Foundation']['Exterior Vertical Insulation']['Thickness']/fThisCond)

# Calculate the Sag of the wall
fSagWallFdn = (1.0/fRWall)*fAgArea

# Call KIVA
filename_tmp = sInFile.rsplit( ".", 1 )[ 0 ]
filename_tmp = filename_tmp+'.csv'
cmd = '"'+KIVAPATH+'"'+' '+sInFile+' '+sCliFile+' '+filename_tmp
os.system(cmd)


# Load in the KIVA results
df = pd.read_csv(filename_tmp, skiprows=0)

# Slice out the total foundation heat loss
fTotFdnLoss=df.loc[:,' Foundation Total Heat Transfer Rate [W]']

# Estimate the below-grade only heat loss at each timestep
fBgFdnLoss = fTotFdnLoss.copy()
for i in range(0, len(fDBtemps), 1):
   fBgFdnLoss[i] -= (fSagWallFdn*(fBsmtTemp-fDBtemps[i]))

# Run the FFT on the below-grade heat loss
fBgFdnLoss = fBgFdnLoss.values
iSamples = len(fBgFdnLoss)
fourierTransform = np.fft.rfft(fBgFdnLoss)
fourierTransform = fourierTransform/float(iSamples)
tempMagnitudes=abs(fourierTransform)

# Get the shape factors and phase
fSbgMean = tempMagnitudes[0]/(fBsmtTemp-fTmean)
fSbgAmp = (tempMagnitudes[1]*2.0)/fTamp
fSbgPhase = np.angle(fourierTransform[1])+math.pi+fPhase

# Write the report file
now = datetime.now()

current_time = now.strftime("%Y-%m-%d %I:%M %p")
fh = open(sOutFile, 'w', encoding="ascii")
print('Created: '+current_time, file = fh)
print('Input file: '+sInFile, file = fh)
print('Climate file: '+sCliFile, file = fh)
print("--------------------------", file = fh)
print("Climate Parameters", file = fh)
print('--------------------------', file = fh)
print('  Average temperature [oC]: '+str(fTmean), file = fh)
print('  Temperature amplitude [oC]: '+str(fTamp), file = fh)
print('  Temperature phase [rad]: '+str(fPhase), file = fh)
print("\n--------------------------", file = fh)
print("Foundation Parameters", file = fh)
print('--------------------------', file = fh)
print('  Above-grade shape factor, S_ag [W/K]: '+str(fSagWallFdn), file = fh)
print('  Below-grade average shape factor, S_bg,avg [W/K]: '+str(fSbgMean), file = fh)
print('  Below-grade amplitude shape factor, S_bg,var [W/K]: '+str(fSbgAmp), file = fh)
print('  Below-grade phase [rad]: '+str(fSbgPhase), file = fh)

fh.close()
