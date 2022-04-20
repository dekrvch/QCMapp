from matplotlib import offsetbox
import numpy as np
import pandas as pd
from bokeh.models import ColumnDataSource
from pybase64 import b64decode
import io
import re
import scipy.stats as st
from sklearn.ensemble import AdaBoostRegressor

from sklearn.exceptions import NonBLASDotWarning

UNITS = ["dfn", "dmn", "dGn"]
OVERTONES = [1,3,5,7,9,11,13]
FREQ2MASS = 17.94 #convet delta freq to delta mass 

class Database:
    TIME_WINDOW = 60 #s, average data for the last x s    
    @staticmethod
    def parseFileName(filename):
        """ Returns a list [datetime, mode, name, stage, comment]
                datetime: TimeStamp
                mode: "weigh"
                name: String
                stage: String
                comment: String            
        """
        try:
            channel = re.findall("-CH[1-4]{1}.txt", filename)[0][3:-4] #Fragment between "-CH" and ".txt"
            channel = int(channel)
        except:
            raise Exception("Cannot determine the channel: {}".format(filename))

        try:
            datetime, mode, names, stages =  filename.split("#")[0].split()
        except:
            raise Exception("Wrong filename format: {}".format(filename))
        datetime = pd.to_datetime(datetime, format = "%Y%m%d_%H%M%S")
        
        if not mode == "weigh":
            raise Exception("Mode is not weigh: {}".format(filename))

        names = names.split("-")
        if len(names) != 4:
            raise Exception("Filename must have 4 sample names specified: {}".format(filename))
        else:
            name = names[channel-1]

        stages = stages.split("-")
        if len (stages) == 1:
            stage = stages[0]
        elif len(stages) == 4:
            stage = stages[channel-1]
        else:
            raise Exception("Filename must have 1 or 4 stages specified: {}".format(filename))

        if "#" in filename:
            commentStart = filename.find("#") + 1
            comment = filename[commentStart:-8]
        else:
            comment = None
        return [datetime, mode, name, stage, comment]
   
    @staticmethod
    def readMeasurement(file):
        
        """ Returns a list [temperature, [f(1)...f(13)], [Gamma(1)...Gamme(13)]]
            temperature: float rounded to 0.1
            f: float
            gamma: float
        """    
        decoded = b64decode(file)
        reading = io.BytesIO(decoded)
        reading = pd.read_csv(reading, sep="\t", skiprows=9)
        time = reading["Time_n=1_(s)"].values
        mask = (time[-1] - time) < Database.TIME_WINDOW #mask to filter the values in the last timeWindw
        averaged = reading[mask].mean()
        
        temp = averaged["Temperature_n=1_(oC)"]
        temp = round(temp, 1)
        
        frecs = []
        gammas = []
        for n in OVERTONES:
            frecs.append(averaged["F_n={}_(Hz)".format(n)]/n)
            gammas.append(averaged["Gamma_n={}_(Hz)".format(n)]/n)
        return [temp, frecs, gammas]
    def __init__(self):
        self.data = pd.DataFrame([], columns=["dateTime", "mode", "comment",  "name", "stage", "temp", "type", "n", "fn", "Gn"])
    
    def build(self, filenames, files):    
        """"
        Builds database as a DataFrame [dateTime, mode, comment, name, stage, temp, n, fn, Gn]
        """
        newDatabase = []
        for filename, file in zip(filenames, files):
            if "weigh" in filename:
                datetime, mode, name, stage, comment = Database.parseFileName(filename)
                temp, freqs, gammas = Database.readMeasurement(file)
                for x in zip(OVERTONES, freqs, gammas):
                    newDatabase.append([datetime, mode, comment, name, stage, temp, "meas", *x])
            else:
               raise Exception("Mode is not weigh: {}".format(filename))
        newDatabase = pd.DataFrame(newDatabase, columns=["dateTime", "mode", "comment",  "name", "stage", "temp", "type", "n", "fn", "Gn"])
        self.data = newDatabase
        
    def getNames(self):
        return list(np.sort(self.data.name.unique()))

    def getTemps(self, name):
        filtered = self.data[self.data.name==name]
        return list(np.sort(filtered.temp.unique()))

    def getStages(self, name, temp):
        filtered = self.data[(self.data.name==name) &
                        (self.data.temp==temp)]
        return list(np.sort(filtered.stage.unique()))

class Sample:
    name = None
    temp = None
    stages = [None]
    ref = None
    ns = OVERTONES
    database =  None
    
    meas = pd.DataFrame()
    stat = pd.DataFrame()
    mass = pd.DataFrame()
    
    def __init__(self, database):
        self.database = database
        self.clear()
    
    def clear(self):
        self.meas = pd.DataFrame([], columns=["dateTime", "mode", "comment",  "name", "stage", "temp", "type", "n", "fn", "Gn",
                                                                                                     "dfn", "dmn", "dGn"])
        self.stat = pd.DataFrame([], columns=["n_", "lower95_dfn", "lower95_dmn", "lower95_dGn", "upper95_dfn", "upper95_dmn", "upper95_dGn"])
        self.mass = pd.DataFrame()
    
    def getStat(self, grouped, alpha):
        """Return mean, std, delta to determine CI"""
        #Calculating Stat
        mean = grouped.mean()[["dfn", "dmn", "dGn"]]
        std  = grouped.std()[["dfn", "dmn", "dGn"]]
        count = grouped.count()[["dfn", "dmn", "dGn"]]
        #Calculate t-value for CI
        t = count.applymap(lambda x: st.t.ppf(q=alpha, df=x-1))
        delta = t*std/count**0.5
        return mean, std, delta
        
    def process(self):
        if not None in [self.name, self.temp]: #Check if all paramteres were defined
            wData = self.database.data
            self.meas = wData[(wData.name == self.name) & 
                            (wData.temp  == self.temp) & 
                            wData.stage.isin(self.stages)&
                            wData.n.isin(self.ns)]
            mean = self.meas.groupby(["stage", "n"]).mean()
            self.meas.insert(10, "dfn",
                                self.meas["fn"]  - self.meas.n.apply(lambda n: mean.fn[self.ref, n]))
            self.meas.insert(11, "dmn",
                                0-self.meas["dfn"]*FREQ2MASS)
            self.meas.insert(12, "dGn",
                                self.meas["Gn"]  - self.meas.n.apply(lambda n: mean.Gn[self.ref, n]))
            
            mean, std, delta = self.getStat(self.meas.groupby(["stage", "n"]), 0.95)
            self.stat  = pd.concat({"mean":mean, "std": std,
                                        "lower95":mean-delta, "upper95":mean+delta}, axis=1).reset_index()
            
            self.calculateMass()    
        else:
            
            raise("Sample not defined: {} {} {} {} {} {}".format(self.name, self.temp, self.stages, self.ref, self.ns, self.database))
        
    def calculateMass(self):
        avrg = self.meas.groupby(["dateTime", "stage"]).mean() #average over all overtones
        mean, std, delta = self.getStat(avrg.groupby(["stage"]), 0.95)
        self.mass = pd.concat({"mean":mean["dmn"], "delta": delta["dmn"]}, axis=1).reset_index()
 
class Dosing:    
    def __init__(self):
        #Initialize to avoid Bokeh Errors in the beginning due to non-existing columnd
        self.clear()
    
    def clear(self):
        self.dateTime = None
        self.name = None
        self.stage = None
        self.adsorbate = None
        self.comment = None
        self.temp = None
        self.ns = OVERTONES
        self.data = pd.DataFrame([], columns=["time"]+[unit[:2]+str(n) for n in OVERTONES for unit in UNITS]
                                 +["df_avg", "dm_avg", "dG_avg"])
        self.selected = pd.DataFrame([], columns=["time"]+[unit[:2]+str(n) for n in OVERTONES for unit in UNITS]
                                      +["df_avg", "dm_avg", "dG_avg"]) #selected overtones
    
    def parseFileName(self, filename):
        """ Returns a list [datetime, mode, name, stage, comment]
            datetime: TimeStamp
            mode: String "dose"
            name: String
            stage: String
            comment: String            
        """
        channel = re.findall("-CH[1-4]{1}.txt", filename)[0][3:-4] #Fragment between "-CH" and ".txt"
        if channel in ["1", "2", "3", "4"]:
            channel = int(channel)
        else:
            raise Exception("Cannot determine the channel: {}".format(filename))

        try:
            datetime, mode, names, stages, adsorbate =  filename.split("#")[0].split()
        except:
            raise Exception("Wrong filename format: {}".format(filename))
        datetime = pd.to_datetime(datetime, format = "%Y%m%d_%H%M%S")
        
        if not mode == "dose":
            raise Exception("Mode is not dosing: {}".format(filename))

        names = names.split("-")
        if len(names) != 4:
            raise Exception("Filename must have 4 sample names specified: {}".format(filename))
        else:
            name = names[channel-1]

        stages = stages.split("-")
        if len (stages) == 1:
            stage = stages[0]
        elif len(stages) == 4:
            stage = stages[channel-1]
        else:
            raise Exception("Filename must have 1 or 4 stages specified: {}".format(filename))

        if "#" in filename:
            commentStart = filename.find("#") + 1
            comment = filename[commentStart:-8]
        else:
            comment = None
        return [datetime, mode, name, stage, adsorbate, comment]
    
    def readMeasurement(self, file):
        """ Returns a list [temperature, [f(1)...f(13)], [Gamma(1)...Gamme(13)]]
            temperature: float rounded to 0.1
            f: float
            gamma: float
        """
        
        decoded = b64decode(file)
        reading = io.BytesIO(decoded)
        reading = pd.read_csv(reading, sep="\t", skiprows=9)
        shortReading = pd.DataFrame()
        shortReading["time"] = reading["Time_n=1_(s)"]
        shortReading["temp"] = reading["Temperature_n=1_(oC)"]
        for n in OVERTONES:
            n = str(n)
            shortReading["df"+n] = reading["Delta_F/n_n={}_(Hz)".format(n)]
            shortReading["dG"+n] = reading["Delta_Gamma/n_n={}_(Hz)".format(n)]
            shortReading["dm"+n] = reading["Delta_Surface_Mass_Density_n={}_(ng/cm2)".format(n)]
        #Calculate AVG
        avg = shortReading.groupby(lambda x: x[0:2]+"_avg", axis=1).mean()[["df_avg", "dm_avg", "dG_avg"]]
        shortReading = pd.concat([shortReading, avg], axis=1)
        return shortReading
    
    def load(self, filename, file):
        if "dose" in  filename:
            self.datetime, mode, self.name, self.stage, self.adsorbate, self.comment = self.parseFileName(filename)
            self.data = self.readMeasurement(file)
            if self.data["temp"].max()-self.data["temp"].min()>0.1:
                raise Exception("Temperature is not constant!")
            self.temp = round( self.data["temp"].mean(), 1)
            self.update()
        else:
            raise Exception("Mode is not dose: {}".format(filename))
    
    def update(self):
        self.selected = self.data[["time"]+[unit[:2]+str(n) for n in self.ns for unit in UNITS]+["df_avg", "dm_avg", "dG_avg"]]
        
class Recipe:
    def __init__(self):
        self.clear()
        self.offset=0
    
    def clear(self):
        self.data = pd.DataFrame([], columns= ["t_0", "t_f", "pp0", "ppm"])
        
    def readFile(self, file):
        decoded = b64decode(file)
        reading = io.BytesIO(decoded)
        reading = pd.read_csv(reading, sep=";", decimal = ",")
        return reading

    def load(self, filename, file):
        reading = self.readFile(file)
        try:
            self.data = reading[["t_0", "t_f", "pp0", "ppm"]]
        except:
            raise Exception("One or more olumns missing: t_0, t_f, pp0, ppm")
    
    def getSteps(self): 
        """Returns (t_0, t_f, pp0, ppm) per step"""
        return [(row["t_0"]+self.offset, row["t_f"]+self.offset,
                 row["pp0"], row["ppm"])
                for i, row in self.data.iterrows() if row["ppm"]>0]
        
    def getLimits(self):
        return (self.data.iloc[0]["t_0"]+self.offset,
                self.data.iloc[-1]["t_f"]+self.offset)
        
class Iso:
    def __init__(self):
        self.name = None
        self.stage = None
        self.adsorbate = None
        self.temp = None
        self.clean()
    
    def clean(self):
        self.data = pd.DataFrame([], columns=["pp0", "ppm"]+[unit[:2]+str(n) for n in OVERTONES for unit in UNITS]
                                      +["d"+u+"_avg" for u in ["f", "m", "G"]]) 
    
    def update(self, dosing, recipe):
        self.name = dosing.name
        self.stage = dosing.stage
        self.adsorbate = dosing.adsorbate
        self.temp = dosing.temp        
        
        self.data = pd.DataFrame([[0]*len(dosing.selected.columns)], columns=dosing.selected.columns)
        if len(dosing.selected) and len(recipe.data) > 0:
            for t_0, t_f, pp0, ppm in recipe.getSteps():
                newRow = pd.Series([pp0, ppm], ["pp0", "ppm"])
                mask = dosing.selected["time"]<t_f
                newRow = pd.concat([newRow, dosing.selected[mask].iloc[-1]])
                self.data = self.data.append(newRow, ignore_index=True)