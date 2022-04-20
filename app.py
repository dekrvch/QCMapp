import pandas as pd
import numpy as np
from dosing_ import update
import qcm
from alert import Alert
from panels import iPanels, wPanels, dPanels
from bokeh.models import Button, FileInput, Select, CheckboxButtonGroup, ColumnDataSource, Legend, Whisker, BoxAnnotation, Slider, PreText, Div, Label, Spacer
from bokeh.events import ButtonClick
from bokeh.models.callbacks import CustomJS
from bokeh.models.widgets import Panel, Tabs, PreText
from bokeh.models.annotations import Title
from bokeh.themes import Theme
from bokeh.plotting import figure, curdoc
from bokeh.layouts import column, row, gridplot
from bokeh.palettes import Category10_10, Plasma
from bokeh.models.tools import HoverTool
from bokeh.server.server import Server
from bokeh.io import export_svg
from tables import Col, Column
import os
from os.path import dirname, join

#Global constants
OVERTONES = [1, 3, 5, 7, 9, 11, 13]
UNITS = ["dfn", "dmn", "dGn"]
UNIT_LABELS = {"dfn":("Δfₙ/n", "Hz"), "dmn":("Δmₙ", "ng/cm²"), "dGn":("ΔΓₙ/n", "Hz")}

#Initialize objects
alert = Alert()
database = qcm.Database()
sample = qcm.Sample(database)
dosing = qcm.Dosing()
recipe = qcm.Recipe()
iso = qcm.Iso()

#Widget Handlers
def loadDatabase(empty=False):
    filenames = inputDatabase.properties_with_values()["filename"]
    files = inputDatabase.properties_with_values()["value"]
    try:
        if len(filenames)==0:
            raise Exception("No files chosen")
        unlock() #unlock to prevent undefined behaviour
        database.build(filenames, files)
        print("Updated Database") 
        updateName("rebuild", None, None)
        if dosing.name!= None: #checked if must be locked at the end
            lock()       
    except:
        alert.throw()
        
def updateName(attr, old, new):
    """
    If attr="rebuild, take the Select options from the database
    If new value doesn't exist, select an empty name
    """
    selectName.remove_on_change("value", updateName) #temporarily remove the handler
    if attr=="rebuild":
        selectName.options = database.getNames()
        selectName.options.append("⠀") #empty name
        selectName.value = selectName.options[0]
    if attr=="value":
        if new in selectName.options:
            selectName.value = new
        else:
            selectName.value ="⠀"        
    selectName.on_change("value", updateName) #put the handler back
    sample.name = selectName.value #assign name the sample object
    print("Sample name:\t{}".format(sample.name))
    updateTemp("rebuild", None, None)
    

def updateTemp(attr, old, new):
    selectTemp.remove_on_change("value", updateTemp) #temporarily remove the handler
    if sample.name=="⠀":
        selectTemp.options = []
        selectTemp.value = None
        sample.temp = None
    elif attr=="rebuild":
        selectTemp.options = [str(temp) for temp in database.getTemps(sample.name)]
        selectTemp.value = selectTemp.options[0]
        sample.temp = float(selectTemp.value)   
    else:
        sample.temp = float(selectTemp.value)       
    selectTemp.on_change("value", updateTemp) #put the handler back        
    print("Updated Temp:\t{}".format(sample.temp))
    updateStages("rebuild", None, None)

        
def updateStages(attr, old, new):
    selectStages.remove_on_change("active", updateStages) #temporarily remove the handler
    if attr=="rebuild":
        pass
        selectStages.labels = database.getStages(sample.name, sample.temp)
        if len(selectStages.labels)==0:
            selectStages.labels.append("⠀") #to prevent disappearing from the GUI
        selectStages.active = [i for i in range(len(selectStages.labels))]    
    elif attr=="active":
         selectStages.active = new
    sample.stages = [selectStages.labels[i] for i in selectStages.active] 
    selectStages.on_change("active", updateStages)  #put the handler back           
    print("Updated Stages:\t{}".format(sample.stages))
    updateRef("rebuild", None, None)

    
def updateRef(attr, old, new):
    selectRef.remove_on_change("value", updateRef) #temporarily remove the handler
    if attr=="rebuild":
        selectRef.options = sample.stages
        if len(selectRef.options) == 0:
            pass
        elif "blank" in selectRef.options:
            selectRef.value = "blank"
        else:
            selectRef.value = selectRef.options[0]
    selectRef.on_change("value", updateRef) #put the handler back
    sample.ref = selectRef.value
    print("Updated Ref:\t{}\n".format(sample.ref))
    updateWeighing()

def updateN():
    sample.ns = [int(selectNs.labels[i]) for i in selectNs.active]
    if sample.name != None: #Only update weighing if a sample is loaded
        updateWeighing()
    dosing.ns = [int(selectNs.labels[i]) for i in selectNs.active] 
    if dosing.name != None: #Only update weighing if dosing data is loaded
        updateDosing()
        
def updateWeighing():
    try:
        pass
    except:
        alert.throw()
    if sample.name=="⠀":
        sample.clear()     
    else:
        sample.process()   
    wpans.update(sample)
    wMeasCSV.text=sample.meas.to_csv(sep=";")
    wStatCSV.text=sample.stat.to_csv(sep=";")
    
    sampleMassString = """
    <p>    
    Mass calculated from Sauebrey eq.
    <div style="margin-left:50px">
    <table class="tg">"""
    for i, row in sample.mass.iterrows():
        sampleMassString+=""" 
        <thead>
        <tr>
        <th class="styleA">{}:</th> 
        <td class="styleB">{:.0f}:</td>
        <td class="styleA">± {:.0f} ng/cm²</td>
        </tr>
        </thead>
        """.format(row["stage"], row["mean"], row["delta"])    
    sampleMassString += r"""</table></div>"""
    wDiv.text = wString + sampleMassString

#Initialize Widgets
inputDatabase = FileInput(accept=".txt", multiple = True)
inputDatabase.on_change("filename", lambda attr, old, new: loadDatabase())

selectName = Select(title="Sample Name", value=None, options=[None])
selectTemp = Select(title="Temperature, °C", value=None, options=[None])
selectStages = CheckboxButtonGroup(labels=["⠀"])
selectRef = Select(title="Reference Stage", value=None, options=[None])

selectName.on_change("value", updateName)
selectTemp.on_change("value", updateTemp)
selectStages.on_change("active", updateStages)
selectRef.on_change("value",updateRef)

selectNs = CheckboxButtonGroup(labels=[str(n) for n in OVERTONES])
selectNs.active = [i for i in range(len(OVERTONES))]
selectNs.on_change("active", lambda attr, old, new: updateN())

wpans = wPanels(sample, UNITS)
wtabs = Tabs(tabs=wpans.getPanels())

#Download Weighing Data
wMeasCSV = Div()
dlMeas = Button(label="Download Measured Data", button_type="primary")
dlMeas.js_on_event("button_click", CustomJS(args=dict(csvString=wMeasCSV,
                                                      title=wpans.title,
                                                      type="meas"),
                            code=open(join(dirname(__file__), "download.js")).read()))
wStatCSV = Div()
dlStat = Button(label="Download Statistics", button_type="primary")
dlStat.js_on_event("button_click", CustomJS(args=dict(csvString=wStatCSV,
                                                      title=wpans.title,
                                                      type="stat"),
                            code=open(join(dirname(__file__), "download.js")).read()))

#Text in the right column
wString = r"""  
    <p align="justify">
    Confidence intervals (95%) calculated according to:
    <p align="center">
    $$
    \bar{X} \pm t(0.95, n-1)\frac{\sigma}{\sqrt{n}}\ ,
    $$
    <p align="justify">
    where $$\bar{X}$$ is the average, $$t$$ is the t-score (Student's distribution),
    $$n$$ is the number of measurements, and $$\sigma$$ is the standard deviation.</p>
    <style type="text/css">
    .tg .styleA{text-align:left;vertical-align:top}
    .tg .styleB{text-align:right;vertical-align:top}
    </style>
    """
wDiv = Div(text=wString)


########################
#Dosing-Iso Data

#Need a generator of inputDosing and inoutRecipe button to replace them when clearDosing() is called
def makeInputDosing():
    inputDosing = FileInput(accept=".txt", multiple = False)
    inputDosing.on_change("filename", lambda attr, old, new: loadDosing())
    return inputDosing

def makeInputRecipe():
    inputRecipe = FileInput(accept=".csv", multiple = False)
    inputRecipe.on_change("filename", lambda attr, old, new: loadRecipe())
    return inputRecipe

def unlock():
    """Unlock sample"""
    selectName.disabled = False
    selectStages.disabled = False
    
def lock():
    """Lock the corresponding sample in weighing mode"""
    unlock()
    updateName("value", None, dosing.name)
    selectName.disabled = True
    selectStages.disabled = True

def clear():
    unlock()
    global inputDosing, inputRecipe
    dosing.clear()
    recipe.clear()
    inputDosing = makeInputDosing()
    dLeft.children[1] = inputDosing
    inputRecipe = makeInputRecipe()
    dLeft.children[3] = inputRecipe
    updateDosing()

def loadDosing():
    print("Update Dosing")
    filename = inputDosing.properties_with_values()["filename"]
    file = inputDosing.properties_with_values()["value"]
    #try:
    dosing.load(filename, file)
    lock()
        #updateDosing()
    #except:
    #    alert.throw()
    updateDosing()
    
def loadRecipe():
    filename = inputRecipe.properties_with_values()["filename"]
    file = inputRecipe.properties_with_values()["value"]
    #try:
    recipe.load(filename, file)
        #updateDosing()
    #except:
    #    alert.throw()
    updateDosing()

def updateOffset(attr, new, old):
    if attr=="value":
        recipe.offset=new
    updateDosing()
    
def updateDosing():
    dosing.update()
    iso.update(dosing, recipe)
    dpans.update(dosing, recipe)
    ipans.update(iso)
    iCSV.text=iso.data.to_csv(sep=";")

clearButton = Button(label="Clear files", button_type="primary")
clearButton.on_click(clear)

inputDosing = makeInputDosing()
inputRecipe = makeInputRecipe() 
selectOffset = Slider(start=0, end=60, value=30, step=5, title="Time offset, s")
selectOffset.on_change("value", updateOffset)

dLeft = column(Div(text="Dosing file"), inputDosing,
                   Div(text="Recipe file"), inputRecipe,
                   clearButton,
                   selectOffset)

dpans = dPanels(dosing, recipe, UNITS)
ipans = iPanels(iso, UNITS)
diTabs = Tabs(tabs=dpans.getPanels()+ipans.getPanels())  

#Download Weighing Data
iCSV = Div()
dlIso = Button(label="Download Isotherms", button_type="primary")
dlIso.js_on_event("button_click", CustomJS(args=dict(csvString=iCSV,
                                                      title=ipans.title,
                                                      type="iso"),
                            code=open(join(dirname(__file__), "download.js")).read()))  

#Text in the right column
iString = r"""  
    <p align="justify">
    Check that the offset time is correct.
    Isotherm calculated for every overtones separately. 
    """
iDiv = Div(text=iString)
iRight = column(dlIso, iDiv)

def qcmApp(doc):
    doc.theme = Theme("theme.yaml")
    alert.add2doc(doc)
    #Weighing
    doc.add_root(Div(text="""<font size="+10">Weighing Mode</font> """, width=600))
    wLeft = column(Div(text="Weighing files"),
                   inputDatabase,selectName, selectTemp,
                   Div(text="Stages"), selectStages, selectRef,
                   Div(text="Overtones"), selectNs)
    wRight = column(dlMeas, dlStat,
                    wDiv)
    doc.add_root(row(wLeft, wtabs, wRight))
    doc.add_root(Spacer(height=50))
    #Dosing Raw
    doc.add_root(Div(text="""<font size="+9">Dosing & Isotherms</font> """, width=600))
    doc.add_root(row(dLeft, diTabs, iRight))
    
    
# Setting num_procs here means we can't touch the IOLoop before now, we must
# let Server handle that. If you need to explicitly handle IOLoops then you
# will need to use the lower level BaseServer class.
server = Server({'/': qcmApp}, num_procs=1)
server.start()
if __name__ == '__main__':
    print('Opening Bokeh application on http://localhost:5006/')

    server.io_loop.add_callback(server.show, "/")
    server.io_loop.start()