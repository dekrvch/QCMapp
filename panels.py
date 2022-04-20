from matplotlib.pyplot import box
import pandas as pd
import numpy as np
from bokeh.models import Button, FileInput, Select, CheckboxButtonGroup, ColumnDataSource, Legend, Whisker, BoxAnnotation, Slider, Range1d
from bokeh.models.callbacks import CustomJS
from bokeh.models.widgets import Panel, Tabs, PreText
from bokeh.models.annotations import Title
from bokeh.themes import Theme
from bokeh.plotting import figure, curdoc
from bokeh.models.renderers import GlyphRenderer
from bokeh.layouts import column, row, gridplot
from bokeh.palettes import Category10_10, Plasma
from bokeh.models.tools import HoverTool
from bokeh.server.server import Server
from bokeh.io import export_svg
from tables import Col, Column

OVERTONES = [1, 3, 5, 7, 9, 11, 13]
UNIT_LABELS = {"dfn":("Δfₙ/n", "Hz"), "dmn":("Δmₙ", "ng/cm²"), "dGn":("ΔΓₙ/n", "Hz")}

WIDTH = 600
HEIGHT = 350
BACKEND = "svg"

class wPanels:
    def __init__(self, sample, units):
        self.panels = {unit:Panel() for unit in units}
        self.meas = ColumnDataSource(sample.meas)
        self.meas.data["color"] = [] #To initiate the color column
        self.stat = ColumnDataSource(sample.stat)
        self.title = Title(text="⠀")
        
        for unit in units:
            pan = self.panels[unit]
            pan.child = self.makeFig(unit)
            pan.title = UNIT_LABELS[unit][0] + " – t"
    
    def getPanels(self):
        return [pan for unit, pan in self.panels.items()]
        
    def makeFig(self, unit):
        fig = figure(width=WIDTH, height=HEIGHT,
                     output_backend=BACKEND)
        fig.title = self.title
        fig.xaxis.ticker = OVERTONES
        fig.xaxis.axis_label = "Overtones"
        fig.yaxis.axis_label = "{}, {}".format(*UNIT_LABELS[unit])
        fig.add_layout(Legend(), "right")
        fig.circle(x="n", y=unit, color="color", legend_field="stage",
                                        source=self.meas, size=5)
        #Whiskers
        whisk = Whisker(source = self.stat, base="n_",
                                            lower="lower95_"+unit, upper="upper95_"+unit)
        fig.add_layout(whisk)    
        #Unvisible circles to keep automatic scaling alright for the Whiskers
        for band in ["lower95", "upper95"]:
            fig.circle(x="n_", y=band+"_"+unit, color="red", alpha=0,
                                        source = self.stat) 
        
        fig.add_tools(HoverTool(
            tooltips=[("date", "@dateTime{%Y-%m-%d %H:%M:%S}"),
                    ("#", "@comment"),
                    ("Δfₙ", "@dfn{+0.0} Hz"),
                    ("Δmₙ", "@dmn{+0.0} ng/cm²"),
                    ("ΔΓₙ", "@dGn{+0.0} Hz")],
            formatters={'@dateTime': 'datetime'}
        )) 
        return fig
    
    def update(self, sample):
            #self.meas and self.stat are CSD, whereas sample.meas and sample.stat are DataFrames
        #Determine colors
        palette = iter(Category10_10)
        stage2Colors = {stage:next(palette) if stage!=sample.ref else "darkslategray" for stage in sample.stages}
        colors =  sample.meas.stage.apply(lambda stage: stage2Colors.get(stage, "darkslategray"))
        colors.name = "color"
        self.meas.data = pd.concat([sample.meas, colors], axis=1)
        self.stat.data = sample.stat
        #Update Title
        if sample.name=="⠀":
            self.title.text = ""
        else:
            self.title.text = "{} at {} °C".format(sample.name, sample.temp)
    
    
class dPanels():
    def __init__(self, dosing, recipe, units):
        self.panels = {unit:Panel() for unit in units}
        self.figs = {unit:figure() for unit in units}
        self.source = ColumnDataSource(dosing.selected)
        self.boxes = []
        self.title = Title(text="")
        # self.xrange = Range1d() 
        self.update(dosing, recipe)         
        for unit in units:
            pan = self.panels[unit]
            pan.child = self.makeFig(unit)
            pan.title = UNIT_LABELS[unit][0] + " – t"
    
    def generateBoxes(self, n):
        newBoxes = [BoxAnnotation(fill_alpha=0.15, fill_color="steelblue") 
                   for i in range(n)]
        for unit, fig in self.figs.items():
            for box in newBoxes:
                fig.add_layout(box)
        self.boxes.extend(newBoxes)
    
    def getPanels(self):
        return [pan for unit, pan in self.panels.items()]     
    
    def makeFig(self, unit):
        """Generate a fig for each unit"""
        fig = figure(width=WIDTH, height=HEIGHT,
            output_backend=BACKEND)
        fig.title = self.title
        palette = dict(zip(OVERTONES, Plasma[10][:7])) #colors by overtone
        fig.add_layout(Legend(), "right")            
        fig.xaxis.axis_label = "Time, s"
        fig.yaxis.axis_label = "{}, {}".format(*UNIT_LABELS[unit])
        # fig.x_range = self.xrange
        for n in OVERTONES:
            fig.line(x="time", y=unit[:2]+str(n), color=palette[n], legend_label=str(n),
                                            source=self.source)
        self.figs[unit] = fig
        return fig
        
    def update(self, dosing, recipe):
        #Title
        if dosing.name != None:
            title = "{} over {}, {} at {} °C".format(dosing.adsorbate, dosing.name, dosing.stage, dosing.temp)
        else:
            title = "⠀"
        self.title.text = title[0].capitalize() + title[1:]
        #Boxes
        steps = recipe.getSteps()
        #Generate extra boxes, if not enough
        if len(self.boxes)<len(steps):
            print("Generating extra boxes:\t{}\n".format(len(steps)-len(self.boxes)))
            self.generateBoxes(len(steps)-len(self.boxes)) 
        #Edit boxes to show t_0 and t_f
        for i in range(len(self.boxes)):
            box = self.boxes[i]
            if i<len(steps):
                box.left, box.right, ppm, pp0 = steps[i]
            else:
                box.left, box.right = None, None
        #X range
        # if len(dosing.selected)>0 and len(recipe.data)==0: 
        #     self.xrange.start, self.xrange.end = (0, dosing.selected.iloc[-1]["time"])
        # elif len(recipe.data)>0:
        #     self.xrange.start, self.xrange.end = recipe.getLimits()
        #Data
        self.source.data = dosing.selected

class iPanels():
    def __init__(self, iso, units):
        self.panels = {unit:Panel() for unit in units}
        self.figs = {unit:figure() for unit in units}
        self.title = Title(text="")
        self.source = ColumnDataSource(iso.data)  
        for unit in units:
            pan = self.panels[unit]
            pan.child = self.makeFig(unit)
            pan.title = UNIT_LABELS[unit][0]+" – p"
      
    def getPanels(self):
        return [pan for unit, pan in self.panels.items()]     
    
    def makeFig(self, unit):
        """Generate a fig for each unit"""
        fig = figure(width=WIDTH, height=HEIGHT,
            output_backend=BACKEND)
        fig.title = self.title
        palette = dict(zip(OVERTONES, Plasma[10][:7])) #colors by overtone
        fig.add_layout(Legend(), "right")            
        fig.xaxis.axis_label = "pp0"
        fig.yaxis.axis_label = "{}, {}".format(*UNIT_LABELS[unit])
        for n in OVERTONES:
            fig.line(x="pp0", y=unit[:2]+str(n), color=palette[n], legend_label=str(n),
                                            source=self.source)
            fig.circle(x="pp0", y=unit[:2]+str(n), color=palette[n], legend_label=str(n), size=5,
                                            source=self.source)
        self.figs[unit] = fig
        return fig
        
    def update(self, iso):
        #Title
        if iso.name != None:
            title = "{} over {}, {} at {} °C".format(iso.adsorbate, iso.name, iso.stage, iso.temp)
        else:
            title = "⠀"
        self.title.text = title[0].capitalize() + title[1:]
        #Data
        self.source.data = iso.data        
        
            