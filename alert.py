import sys
from bokeh.io import curdoc
from bokeh.models.widgets import TextInput
from bokeh.models.callbacks import CustomJS
from bokeh.models.sources import ColumnDataSource

class Alert:
    callback = CustomJS(args=dict(source=ColumnDataSource()), code="""
        alert('Empty callback');
    """)

    phantom = TextInput(value="default", title="Phantom",  visible = False)
    phantom.js_on_change('value', callback)
    
    def add2doc(self, doc):
        doc.add_root(self.phantom)
    
    def throw(self):
        message = str(sys.exc_info()[1])
        js_code = """
                    alert('{}');
                """.format(message)
        self.callback.code = js_code
        self.phantom.value = self.phantom.value+"n"

