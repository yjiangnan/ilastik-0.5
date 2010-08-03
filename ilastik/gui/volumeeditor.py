#!/usr/bin/env python
# -*- coding: utf-8 -*-

#    Copyright 2010 C Sommer, C Straehle, U Koethe, FA Hamprecht. All rights reserved.
#    
#    Redistribution and use in source and binary forms, with or without modification, are
#    permitted provided that the following conditions are met:
#    
#       1. Redistributions of source code must retain the above copyright notice, this list of
#          conditions and the following disclaimer.
#    
#       2. Redistributions in binary form must reproduce the above copyright notice, this list
#          of conditions and the following disclaimer in the documentation and/or other materials
#          provided with the distribution.
#    
#    THIS SOFTWARE IS PROVIDED BY THE ABOVE COPYRIGHT HOLDERS ``AS IS'' AND ANY EXPRESS OR IMPLIED
#    WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND
#    FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE ABOVE COPYRIGHT HOLDERS OR
#    CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
#    CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
#    SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
#    ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
#    NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF
#    ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#    
#    The views and conclusions contained in the software and documentation are those of the
#    authors and should not be interpreted as representing official policies, either expressed
#    or implied, of their employers.

"""
Dataset Editor Dialog based on PyQt4
"""
import qimage2ndarray.qimageview
import math

try:
    from OpenGL.GL import *
    from OpenGL.GLU import *
except Exception, e:
    print e
    pass

from PyQt4 import QtCore, QtGui, QtOpenGL
import sip
import vigra, numpy
import qimage2ndarray
import h5py
import copy
import os.path
from collections import deque
import threading
import traceback
import os, sys

from enthought.mayavi import mlab
from enthought.traits.api import HasTraits, Range, Instance, on_trait_change
from enthought.traits.ui.api import View, Item, Group

from enthought.mayavi.core.api import PipelineBase
from enthought.mayavi.core.ui.api import MayaviScene, SceneEditor, MlabSceneModel

from shortcutmanager import *

# Local import
#from spyderlib.config import get_icon, get_font

##mixin to enable label access
#class VolumeLabelAccessor():
    #def __init__():
        #self._labels = None

##extend ndarray with _label attribute
#numpy.ndarray.__base__ += (VolumeLabelAccessor, )



################################################################################
#The actual visualization
class Maya3DScene(HasTraits):

    scene = Instance(MlabSceneModel, ())

    plot = Instance(PipelineBase)


    def __init__(self, item, raw):
        HasTraits.__init__(self)
        self.item = item
        self.raw = raw
        

    # When the scene is activated, or when the parameters are changed, we
    # update the plot.
    @on_trait_change('scene.activated')
    def update_plot(self):
        if self.plot is None:
            self.dataField = self.scene.mlab.pipeline.scalar_field(self.item.data[0,:,:,:,0])
            self.rawField = self.scene.mlab.pipeline.scalar_field(self.raw.data[0,:,:,:,0])


            self.xp = self.scene.mlab.pipeline.image_plane_widget(self.rawField,
                            plane_orientation='x_axes',
                            slice_index=10
                            )
            def move_slicex(obj, evt):
                #print obj
                print obj.GetCurrentCursorPosition()
                print self.xp.ipw.slice_position

            self.xp.ipw.add_observer('EndInteractionEvent', move_slicex)

            self.yp = self.scene.mlab.pipeline.image_plane_widget(self.rawField,
                            plane_orientation='y_axes',
                            slice_index=10
                        )
            def move_slicey(obj, evt):
                #print obj
                print obj.GetCurrentCursorPosition()
                print self.yp.ipw.slice_position

            self.yp.ipw.add_observer('EndInteractionEvent', move_slicey)

            self.zp = self.scene.mlab.pipeline.image_plane_widget(self.rawField,
                            plane_orientation='z_axes',
                            slice_index=10
                        )
            def move_slicez(obj, evt):
                #print obj
                print obj.GetCurrentCursorPosition()
                print self.zp.ipw.slice_position

            self.zp.ipw.add_observer('EndInteractionEvent', move_slicez)

            self.plot = self.scene.mlab.pipeline.iso_surface(self.dataField, opacity=0.4, contours=[2])
            
            #self.scene.mlab.pipeline.volume(self.scene.mlab.pipeline.scalar_field(self.item.data[0,:,:,:,0]), vmin=0.5, vmax=1.5)
            #self.scene.mlab.outline()
        else:
            self.plot.mlab_source.set(self.item.data[0,:,:,:,0])


    # The layout of the dialog created
    view = View(Item('scene', editor=SceneEditor(scene_class=MayaviScene),
                     height=480, width=640, show_label=False),
                resizable=True

                )


################################################################################
# The QWidget containing the visualization, this is pure PyQt4 code.
class MayaviQWidget(QtGui.QWidget):
    def __init__(self, item, raw):
        QtGui.QWidget.__init__(self)
        layout = QtGui.QVBoxLayout(self)
        layout.setMargin(0)
        layout.setSpacing(0)
        self.visualization = Maya3DScene(item, raw)

        # If you want to debug, beware that you need to remove the Qt
        # input hook.
        #QtCore.pyqtRemoveInputHook()
        #import pdb ; pdb.set_trace()
        #QtCore.pyqtRestoreInputHook()

        # The edit_traits call will generate the widget to embed.
        self.ui = self.visualization.edit_traits(parent=self,
                                                 kind='subpanel').control
        layout.addWidget(self.ui)
        self.ui.setParent(self)

    def closeEvent(self, ev):
        self.ui.setVisible(False)
        mlab.close()

def rgb(r, g, b):
    # use qRgb to pack the colors, and then turn the resulting long
    # into a negative integer with the same bitpattern.
    return (QtGui.qRgb(r, g, b) & 0xffffff) - 0x1000000



class VolumeEditorList(QtCore.QObject):
    editors = None #class variable to hold global editor list

    def __init__(self):
        QtCore.QObject.__init__(self)
        self.editors = []


    def append(self, object):
        self.editors.append(object)
        self.emit(QtCore.SIGNAL('appended(int)'), self.editors.__len__() - 1)

    def remove(self, editor):
        for index, item in enumerate(self.editors):
            if item == editor:
                self.emit(QtCore.SIGNAL('removed(int)'), index)
                self.editors.__delitem__(index)

VolumeEditorList.editors = VolumeEditorList()


class DataAccessor():
    """
    This class gives consistent access to data volumes, images channels etc.
    access is always of the form [time, x, y, z, channel]
    """
    
    def __init__(self, data, channels = False):
        """
        data should be a numpy/vigra array that transformed to the [time, x, y, z, channel] access like this:
            (a,b), b != 3 and channels = False  (0,0,a,b,0)
            (a,b), b == 3 or channels = True:  (0,0,0,a,b)
            (a,b,c), c != 3 and channels = False:  (0,a,b,c,0)
            (a,b,c), c == 3 or channels = True:  (0,0,a,b,c)
            etc.
        """
        if len(data.shape) == 5:
            channels = True
            
        if issubclass(data.__class__, DataAccessor):
            data = data.data
            channels = True
        
        rgb = 1
        if data.shape[-1] == 3 or channels:
            rgb = 0

        tempShape = data.shape

        self.data = data

        if issubclass(data.__class__, vigra.arraytypes._VigraArray):
            for i in range(len(data.shape)/2):
                #self.data = self.data.swapaxes(i,len(data.shape)-i)
                pass
            self.data = self.data.view(numpy.ndarray)
            #self.data.reshape(tempShape)


        for i in range(5 - (len(data.shape) + rgb)):
            tempShape = (1,) + tempShape
            
        if rgb:
            tempShape = tempShape + (1,)

        if len(self.data.shape) != len(tempShape):
            self.data = self.data.reshape(tempShape)
        self.channels = self.data.shape[-1]

        self.rgb = False
        if data.shape[-1] == 3:
            self.rgb = True

        self.shape = self.data.shape


    def __getitem__(self, key):
        return self.data[tuple(key)]
    
    def __setitem__(self, key, data):
        self.data[tuple(key)] = data

    def getSlice(self, num, axis, time = 0, channel = 0):
        if self.rgb is True:
            if axis == 0:
                return self.data[time, num, :,: , :]
            elif axis == 1:
                return self.data[time, :,num,: , :]
            elif axis ==2:
                return self.data[time, :,: ,num,  :]
        else:
            if axis == 0:
                return self.data[time, num, :,: , channel]
            elif axis == 1:
                return self.data[time, :,num,: , channel]
            elif axis ==2:
                return self.data[time, :,: ,num,  channel]
            

    def setSlice(self, data, num, axis, time = 0, channel = 0):
        if self.rgb is True:
            if axis == 0:
                self.data[time, num, :,: , :] = data
            elif axis == 1:
                self.data[time, :,num,: , :] = data
            elif axis ==2:
                self.data[time, :,: ,num,  :] = data
        else:        
            if axis == 0:
                self.data[time, num, :,: , channel] = data
            elif axis == 1:
                self.data[time, :,num,: , channel] = data
            elif axis ==2:
                self.data[time, :,: ,num,  channel] = data

    def getSubSlice(self, offsets, sizes, num, axis, time = 0, channel = 0):
        ax0l = offsets[0]
        ax0r = offsets[0]+sizes[0]
        ax1l = offsets[1]
        ax1r = offsets[1]+sizes[1]

        if self.rgb is True:
            if axis == 0:
                return self.data[time, num, ax0l:ax0r,ax1l:ax1r , :]
            elif axis == 1:
                return self.data[time, ax0l:ax0r, num,ax1l:ax1r , :]
            elif axis ==2:
                return self.data[time, ax0l:ax0r, ax1l:ax1r ,num,  :]
        else:
            if axis == 0:
                return self.data[time, num, ax0l:ax0r,ax1l:ax1r , channel]
            elif axis == 1:
                return self.data[time, ax0l:ax0r, num,ax1l:ax1r , channel]
            elif axis ==2:
                return self.data[time, ax0l:ax0r, ax1l:ax1r ,num,  channel]
            

    def setSubSlice(self, offsets, data, num, axis, time = 0, channel = 0):
        ax0l = offsets[0]
        ax0r = offsets[0]+data.shape[0]
        ax1l = offsets[1]
        ax1r = offsets[1]+data.shape[1]

        if self.rgb is True:
            if axis == 0:
                self.data[time, num,  ax0l:ax0r, ax1l:ax1r , :] = data
            elif axis == 1:
                self.data[time, ax0l:ax0r,num, ax1l:ax1r , :] = data
            elif axis ==2:
                self.data[time, ax0l:ax0r, ax1l:ax1r ,num,  :] = data
        else:
            if axis == 0:
                self.data[time, num,  ax0l:ax0r, ax1l:ax1r , channel] = data
            elif axis == 1:
                self.data[time, ax0l:ax0r,num, ax1l:ax1r , channel] = data
            elif axis ==2:
                self.data[time, ax0l:ax0r, ax1l:ax1r ,num,  channel] = data
     
    def serialize(self, h5G, name='data'):
        h5G.create_dataset(name,data = self.data)
         
    @staticmethod
    def deserialize(h5G, name = 'data'):
        data = h5G[name].value
        return DataAccessor(data, channels = True)
        
class PatchAccessor():
    def __init__(self, size_x,size_y, blockSize = 128):
        self.blockSize = blockSize
        self.size_x = size_x
        self.size_y = size_y

        self.cX = int(numpy.ceil(1.0 * size_x / self.blockSize))

        #last blocks can be very small -> merge them with the secondlast one
        self.cXend = size_x % self.blockSize
        if self.cXend < self.blockSize / 3 and self.cXend != 0 and self.cX > 1:
            self.cX -= 1
        else:
            self.cXend = 0

        self.cY = int(numpy.ceil(1.0 * size_y / self.blockSize))

        #last blocks can be very small -> merge them with the secondlast one
        self.cYend = size_y % self.blockSize
        if self.cYend < self.blockSize / 3 and self.cYend != 0 and self.cY > 1:
            self.cY -= 1
        else:
            self.cYend = 0


        self.patchCount = self.cX * self.cY


    def getPatchBounds(self, blockNum, overlap = 0):
        z = int(numpy.floor(blockNum / (self.cX*self.cY)))
        rest = blockNum % (self.cX*self.cY)
        y = int(numpy.floor(rest / self.cX))
        x = rest % self.cX

        startx = max(0, x*self.blockSize - overlap)
        endx = min(self.size_x, (x+1)*self.blockSize + overlap)
        if x+1 >= self.cX:
            endx = self.size_x

        starty = max(0, y*self.blockSize - overlap)
        endy = min(self.size_y, (y+1)*self.blockSize + overlap)
        if y+1 >= self.cY:
            endy = self.size_y


        return [startx,endx,starty,endy]

    def getPatchesForRect(self,startx,starty,endx,endy):
        sx = int(numpy.floor(1.0 * startx / self.blockSize))
        ex = int(numpy.ceil(1.0 * endx / self.blockSize))
        sy = int(numpy.floor(1.0 * starty / self.blockSize))
        ey = int(numpy.ceil(1.0 * endy / self.blockSize))
        
        
        if ey > self.cY:
            ey = self.cY

        if ex > self.cX :
            ex = self.cX

        nums = []
        for y in range(sy,ey):
            nums += range(y*self.cX+sx,y*self.cX+ex)
        
        return nums

class OverlaySlice():
    """
    Helper class to encapsulate the overlay slice and its drawing related settings
    """
    def __init__(self, data, color, alpha, colorTable):
        self.colorTable = colorTable
        self.color = color
        self.alpha = alpha
        self.alphaChannel = None
        self.data = data

class VolumeOverlay(QtGui.QListWidgetItem, DataAccessor):
    """
    Class to encapsulate the overlay data and its properties
    """
    def __init__(self, data, name = "Red Overlay", color = 0, alpha = 0.4, colorTable = None, visible = True):
        QtGui.QListWidgetItem.__init__(self,name)
        DataAccessor.__init__(self,data)
        self.colorTable = colorTable
        self.setTooltip = name
        self.color = color
        self.alpha = alpha
        self.name = name
        self.visible = visible

	s = None
	if self.visible:
		s = QtCore.Qt.Checked
	else:
		s = QtCore.Qt.Unchecked

        self.setCheckState(s)
        self.oldCheckState = self.visible
        self.setFlags(self.flags() | QtCore.Qt.ItemIsUserCheckable)


    def getOverlaySlice(self, num, axis, time = 0, channel = 0):
        return OverlaySlice(self.getSlice(num,axis,time,channel), self.color, self.alpha, self.colorTable)
                 

class OverlayListWidget(QtGui.QListWidget):

    class QAlphaSliderDialog(QtGui.QDialog):
        def __init__(self, min, max, value):
            QtGui.QDialog.__init__(self)
            self.setWindowTitle('Change Alpha')
            self.slider = QtGui.QSlider(QtCore.Qt.Horizontal, self)
            self.slider.setGeometry(20, 30, 140, 20)
            self.slider.setRange(min,max)
            self.slider.setValue(value)

    def __init__(self,parent):
        QtGui.QListWidget.__init__(self, parent)
        self.volumeEditor = parent
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.connect(self, QtCore.SIGNAL("customContextMenuRequested(QPoint)"), self.onContext)
        self.connect(self, QtCore.SIGNAL("clicked(QModelIndex)"), self.onItemClick)
        self.connect(self, QtCore.SIGNAL("doubleClicked(QModelIndex)"), self.onItemDoubleClick)
        self.overlays = [] #array of VolumeOverlays
        self.currentItem = None

    def onItemClick(self, itemIndex):
        item = self.itemFromIndex(itemIndex)
        if (item.checkState() == QtCore.Qt.Checked and not item.visible) or (item.checkState() == QtCore.Qt.Unchecked and item.visible):
            item.visible = not(item.visible)
            s = None
	    if item.visible:
                s = QtCore.Qt.Checked
            else:
                s = QtCore.Qt.Unchecked
            item.setCheckState(s)
            self.volumeEditor.repaint()
            
    def onItemDoubleClick(self, itemIndex):
        self.currentItem = item = self.itemFromIndex(itemIndex)
        if item.checkState() == item.visible * 2:
            dialog = OverlayListWidget.QAlphaSliderDialog(1, 20, round(item.alpha*20))
            dialog.slider.connect(dialog.slider, QtCore.SIGNAL('valueChanged(int)'), self.setCurrentItemAlpha)
            dialog.exec_()
        else:
            self.onItemClick(self,itemIndex)
            
            
    def setCurrentItemAlpha(self, num):
        self.currentItem.alpha = 1.0 * num / 20.0
        self.volumeEditor.repaint()
        
    def clearOverlays(self):
        self.clear()
        self.overlays = []

    def removeOverlay(self, item):
        itemNr = None
        if isinstance(item, str):
            for idx, it in enumerate(self.overlays):
                if it.name == item:
                    itemNr = idx
                    item = it
        else:
            itemNr = item
        if itemNr != None:
            self.overlays.pop(itemNr)
            self.takeItem(itemNr)
            return item
        else:
            return None

    def addOverlay(self, overlay):
        self.overlays.append(overlay)
        self.addItem(overlay)

    def onContext(self, pos):
        index = self.indexAt(pos)

        if not index.isValid():
           return

        item = self.itemAt(pos)
        name = item.text()

        menu = QtGui.QMenu(self)

        show3dAction = menu.addAction("Display in Mayavi")

        action = menu.exec_(QtGui.QCursor.pos())
        if action == show3dAction:
#            mlab.contour3d(item.data[0,:,:,:,0], opacity=0.6)
#            mlab.outline()
            my_model = MayaviQWidget(item, self.volumeEditor.image)
            my_model.show()


class VolumeLabelDescription():
    def __init__(self, name,number, color):
        self.number = number
        self.name = name
        self.color = color
        self.prediction = None

        
    def __eq__(self, other):
        answer = True
        if self.number != other.number:
            answer = False
        if self.name != other.name:
            answer = False
        if self.color != other.color:
            answer = False
        return answer

    def __ne__(self, other):
        return not(self.__eq__(other))

    def clone(self):
        t = VolumeLabelDescription( self.name, self.number, self.color)
        return t
    
class VolumeLabels():
    """
    Class that manages the different labels (VolumeLabelDescriptions) for one Volume

    can serialize and deserialize into a h5py group
    """
    def __init__(self, data = None):
        if issubclass(data.__class__, DataAccessor):
            self.data = data
        else:
            self.data = DataAccessor(data, channels = False)

        self.descriptions = [] #array of VolumeLabelDescriptions

    def getLabelNames(self):
        labelNames = []
        for idx, it in enumerate(self.descriptions):
            labelNames.append(it.name)
        return labelNames
        
    def serialize(self, h5G, name = "labels"):
        self.data.serialize(h5G, name)
        
        tColor = []
        tName = []
        tNumber = []
        
        for index, item in enumerate(self.descriptions):
            tColor.append(item.color)
            tName.append(str(item.name))
            tNumber.append(item.number)

        if len(tColor) > 0:            
            h5G[name].attrs['color'] = tColor 
            h5G[name].attrs['name'] = tName
            h5G[name].attrs['number'] = tNumber
            
    
    @staticmethod    
    def deserialize(h5G, name ="labels"):
        if name in h5G.keys():
            data = DataAccessor.deserialize(h5G, name)
            colors = []
            names = []
            numbers = []
            if h5G[name].attrs.__contains__('color'):
                colors = h5G[name].attrs['color']
                names = h5G[name].attrs['name']
                numbers = h5G[name].attrs['number']
            descriptions = []
            for index, item in enumerate(colors):
                descriptions.append(VolumeLabelDescription(names[index], numbers[index], colors[index]))
    
            vl =  VolumeLabels(data)
            vl.descriptions = descriptions
            return vl
        else:
            return None
        
class Volume():
    """
    Represents a data volume including labels etc.
    
    can serialize and deserialize into a h5py group
    """
    def __init__(self):
        self.data = None
        self.labels = None
        self.uncertainty = None
        self.segmentation = None
        
    def serialize(self, h5G):
        self.data.serialize(h5G, "data")
        if self.labels is not None:
            self.labels.serialize(h5G, "labels")
        
    @staticmethod
    def deserialize(h5G):
        #TODO: make nicer
        data = DataAccessor.deserialize(h5G)
        labels = VolumeLabels.deserialize(h5G)
        v =  Volume()
        v.data = data
        v.labels = labels
        return v



class LabelListItem(QtGui.QListWidgetItem):
    def __init__(self, name , number, color):
        QtGui.QListWidgetItem.__init__(self, name)
        self.number = number
        self.visible = True
        self.setColor(color)
        #self.setFlags(self.flags() | QtCore.Qt.ItemIsUserCheckable)
        #self.setFlags(self.flags() | QtCore.Qt.ItemIsEditable)

        

    def toggleVisible(self):
        self.visible = not(self.visible)

    def setColor(self, color):
        self.color = color
        pixmap = QtGui.QPixmap(16, 16)
        pixmap.fill(color)
        icon = QtGui.QIcon(pixmap)
        self.setIcon(icon)      


class LabelListWidget(QtGui.QListWidget):
    def __init__(self,parent = None):
        QtGui.QListWidget.__init__(self,parent)
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.connect(self, QtCore.SIGNAL("customContextMenuRequested(QPoint)"), self.onContext)
        self.colorTab = []
        self.items = []
        self.volumeEditor = parent
        self.labelColorTable = [QtGui.QColor(QtCore.Qt.red), QtGui.QColor(QtCore.Qt.green), QtGui.QColor(QtCore.Qt.yellow), QtGui.QColor(QtCore.Qt.blue), QtGui.QColor(QtCore.Qt.magenta) , QtGui.QColor(QtCore.Qt.darkYellow), QtGui.QColor(QtCore.Qt.lightGray)]
        #self.connect(self, QtCore.SIGNAL("currentTextChanged(QString)"), self.changeText)
        self.labelPropertiesChanged_callback = None
    
    def initFromMgr(self, volumelabel):
        self.volumeLabel = volumelabel
        for index, item in enumerate(volumelabel.descriptions):
            li = LabelListItem(item.name,item.number, QtGui.QColor.fromRgb(long(item.color)))
            self.addItem(li)
            self.items.append(li)
        self.buildColorTab()
        
        #just select the first item in the list so we have some selection
        self.selectionModel().setCurrentIndex(self.model().index(0,0), QtGui.QItemSelectionModel.ClearAndSelect)
        
    def changeText(self, text):
        self.volumeLabel.descriptions[self.currentRow()].name = text
        
    def createLabel(self):
        name = "Label " + len(self.items).__str__()
        number = len(self.items)
        if number > len(self.labelColorTable):
            color = QtGui.QColor.fromRgb(numpy.random.randint(255),numpy.random.randint(255),numpy.random.randint(255))
        else:
            color = self.labelColorTable[number]
        number +=1
        self.addLabel(name, number, color)
        self.buildColorTab()
        
    def addLabel(self, labelName, labelNumber, color):
        description = VolumeLabelDescription(labelName, labelNumber, color.rgb())
        self.volumeLabel.descriptions.append(description)
        
        label =  LabelListItem(labelName, labelNumber, color)
        self.items.append(label)
        self.addItem(label)
        self.buildColorTab()
        #self.emit(QtCore.SIGNAL("labelPropertiesChanged()"))
        if self.labelPropertiesChanged_callback is not None:
            self.labelPropertiesChanged_callback()
        
        #select the last item in the last
        self.selectionModel().setCurrentIndex(self.model().index(self.model().rowCount()-1,0), QtGui.QItemSelectionModel.ClearAndSelect)

    def buildColorTab(self):
        self.colorTab = []
        for i in range(256):
            self.colorTab.append(QtGui.QColor.fromRgb(0,0,0).rgb())

        for index,item in enumerate(self.items):
            self.colorTab[item.number] = item.color.rgb()


    def onContext(self, pos):
        index = self.indexAt(pos)

        if not index.isValid():
           return

        item = self.itemAt(pos)
        name = item.text()

        menu = QtGui.QMenu(self)

        removeAction = menu.addAction("Remove")
        colorAction = menu.addAction("Change Color")
        if item.visible is True:
            toggleHideAction = menu.addAction("Hide")
        else:
            toggleHideAction = menu.addAction("Show")

        action = menu.exec_(QtGui.QCursor.pos())
        if action == removeAction:
            self.volumeEditor.history.removeLabel(item.number)
            for ii, it in enumerate(self.items):
                if it.number > item.number:
                    it.number -= 1
            self.items.remove(item)
            it = self.takeItem(index.row())
            del it
            self.buildColorTab()
            self.emit(QtCore.SIGNAL("labelRemoved(int)"), item.number)
            #self.emit(QtCore.SIGNAL("labelPropertiesChanged()"))
            if self.labelPropertiesChanged_callback is not None:
                self.labelPropertiesChanged_callback()
            self.volumeEditor.repaint()
        elif action == toggleHideAction:
            self.buildColorTab()
            item.toggleVisible()
        elif action == colorAction:
            color = QtGui.QColorDialog().getColor()
            item.setColor(color)
            self.volumeLabel.descriptions[index.row()].color = color.rgb()
            
#            self.emit(QtCore.SIGNAL("labelPropertiesChanged()"))
            if self.labelPropertiesChanged_callback is not None:
                self.labelPropertiesChanged_callback()
            self.buildColorTab()
            self.volumeEditor.repaint()

        

#abstract base class for undo redo stuff
class State():
    def __init__(self):
        pass

    def restore(self):
        pass


class LabelState(State):
    def __init__(self, title, axis, num, offsets, shape, time, volumeEditor, erasing, labels, labelNumber):
        self.title = title
        self.time = time
        self.num = num
        self.offsets = offsets
        self.axis = axis
        self.erasing = erasing
        self.labelNumber = labelNumber
        self.labels = labels
        self.dataBefore = volumeEditor.labels.data.getSubSlice(self.offsets, self.labels.shape, self.num, self.axis, self.time, 0).copy()
        
    def restore(self, volumeEditor):
        temp = volumeEditor.labels.data.getSubSlice(self.offsets, self.labels.shape, self.num, self.axis, self.time, 0).copy()
        restore  = numpy.where(self.labels > 0, self.dataBefore, 0)
        stuff = numpy.where(self.labels > 0, self.dataBefore + 1, 0)
        erase = numpy.where(stuff == 1, 1, 0)
        self.dataBefore = temp
        #volumeEditor.labels.data.setSubSlice(self.offsets, temp, self.num, self.axis, self.time, 0)
        volumeEditor.setLabels(self.offsets, self.axis, self.num, restore, False)
        volumeEditor.setLabels(self.offsets, self.axis, self.num, erase, True)
        if volumeEditor.sliceSelectors[self.axis].value() != self.num:
            volumeEditor.sliceSelectors[self.axis].setValue(self.num)
        else:
            #volumeEditor.repaint()
            #repainting is already done automatically by the setLabels function
            pass
        self.erasing = not(self.erasing)          



class HistoryManager(QtCore.QObject):
    def __init__(self, parent, maxSize = 3000):
        QtCore.QObject.__init__(self)
        self.volumeEditor = parent
        self.maxSize = maxSize
        self.history = []
        self.current = -1

    def append(self, state):
        if self.current + 1 < len(self.history):
            self.history = self.history[0:self.current+1]
        self.history.append(state)

        if len(self.history) > self.maxSize:
            self.history = self.history[len(self.history)-self.maxSize:len(self.history)]
        
        self.current = len(self.history) - 1

    def undo(self):
        if self.current >= 0:
            self.history[self.current].restore(self.volumeEditor)
            self.current -= 1

    def redo(self):
        if self.current < len(self.history) - 1:
            self.history[self.current + 1].restore(self.volumeEditor)
            self.current += 1
            
    def serialize(self, grp):
        histGrp= grp.create_group('history')
        for i, hist in enumerate(self.history):
            histItemGrp = histGrp.create_group('%04d'%i)
            histItemGrp.create_dataset('labels',data=hist.labels)
            histItemGrp.create_dataset('axis',data=hist.axis)
            histItemGrp.create_dataset('slice',data=hist.num)
            histItemGrp.create_dataset('labelNumber',data=hist.labelNumber)
            histItemGrp.create_dataset('offsets',data=hist.offsets)
            histItemGrp.create_dataset('time',data=hist.time)
            histItemGrp.create_dataset('erasing',data=hist.erasing)


    def removeLabel(self, number):
        tobedeleted = []
        for index, item in enumerate(self.history):
            if item.labelNumber != number:
                item.dataBefore = numpy.where(item.dataBefore == number, 0, item.dataBefore)
                item.dataBefore = numpy.where(item.dataBefore > number, item.dataBefore - 1, item.dataBefore)
                item.labels = numpy.where(item.labels == number, 0, item.labels)
                item.labels = numpy.where(item.labels > number, item.labels - 1, item.labels)
            else:
                #if item.erasing == False:
                    #item.restore(self.volumeEditor)
                tobedeleted.append(index - len(tobedeleted))
                if index <= self.current:
                    self.current -= 1

        for val in tobedeleted:
            it = self.history[val]
            self.history.__delitem__(val)
            del it

class VolumeUpdate():
    def __init__(self, data, offsets, sizes, erasing):
        self.offsets = offsets
        self.data = data
        self.sizes = sizes
        self.erasing = erasing
    
    def applyTo(self, dataAcc):
        offsets = self.offsets
        sizes = self.sizes
        #TODO: move part of function into DataAccessor class !! e.g. setSubVolume or somethign
        tempData = dataAcc[offsets[0]:offsets[0]+sizes[0],offsets[1]:offsets[1]+sizes[1],offsets[2]:offsets[2]+sizes[2],offsets[3]:offsets[3]+sizes[3],offsets[4]:offsets[4]+sizes[4]].copy()

        if self.erasing == True:
            tempData = numpy.where(self.data > 0, 0, tempData)
        else:
            tempData = numpy.where(self.data > 0, self.data, tempData)
        
        dataAcc[offsets[0]:offsets[0]+sizes[0],offsets[1]:offsets[1]+sizes[1],offsets[2]:offsets[2]+sizes[2],offsets[3]:offsets[3]+sizes[3],offsets[4]:offsets[4]+sizes[4]] = tempData  



class VolumeEditor(QtGui.QWidget):
    """Array Editor Dialog"""
    def __init__(self, image, name="", font=None,
                 readonly=False, size=(400, 300), labels = None , opengl = True, openglOverview = True, embedded = False, parent = None):
        QtGui.QWidget.__init__(self, parent)
        self.name = name
        title = name
        
        self.labelsAlpha = 1.0

        #Bordermargin settings - they control the blue markers that signal the region from wich the
        #labels are not used for trainig
        self.useBorderMargin = False
        self.borderMargin = 0


        #this setting controls the rescaling of the displayed data to the full 0-255 range
        self.normalizeData = False

        #this settings controls the timer interval during interactive mode
        #set to 0 to wait for complete brushstrokes !
        self.drawUpdateInterval = 300

        self.opengl = opengl
        self.openglOverview = openglOverview
        if self.opengl is True:
            #print "Using OpenGL Slice rendering"
            pass
        else:
            #print "Using Software Slice rendering"
            pass
        if self.openglOverview is True:
            #print "Enabling OpenGL Overview rendering"
            pass
        
        self.embedded = embedded


        QtGui.QPixmapCache.setCacheLimit(100000)


        if issubclass(image.__class__, DataAccessor):
            self.image = image
        elif issubclass(image.__class__, Volume):
            self.image = image.data
            labels = image.labels
        else:
            self.image = DataAccessor(image)

       
        if hasattr(image, '_labels'):
            self.labels = image._labels
        elif labels is not None:
            self.labels = labels
        else:
            tempData = DataAccessor(numpy.zeros(self.image.shape[1:4],'uint8'))
            self.labels = VolumeLabels(tempData)

        if issubclass(image.__class__, Volume):
            image.labels = self.labels

            
        self.editor_list = VolumeEditorList.editors

        self.linkedTo = None

        self.selectedTime = 0
        self.selectedChannel = 0

        self.pendingLabels = []

        self.ownIndex = self.editor_list.editors.__len__()
        #self.setAccessibleName(self.name)


        self.history = HistoryManager(self)

        self.layout = QtGui.QHBoxLayout()
        self.setLayout(self.layout)


        self.grid = QtGui.QGridLayout()

        self.drawManager = DrawManager(self)

        self.imageScenes = []
        
        self.imageScenes.append(ImageScene(self, (self.image.shape[2],  self.image.shape[3], self.image.shape[1]), 0 ,self.drawManager))
        self.imageScenes.append(ImageScene(self, (self.image.shape[1],  self.image.shape[3], self.image.shape[2]), 1 ,self.drawManager))
        self.imageScenes.append(ImageScene(self, (self.image.shape[1],  self.image.shape[2], self.image.shape[3]), 2 ,self.drawManager))
        
        self.grid.addWidget(self.imageScenes[2], 0, 0)
        self.grid.addWidget(self.imageScenes[0], 0, 1)
        self.grid.addWidget(self.imageScenes[1], 1, 0)

        if self.openglOverview is True:
            self.overview = OverviewScene(self, self.image.shape[1:4])
        else:
            self.overview = OverviewSceneDummy(self, self.image.shape[1:4])
            
        self.grid.addWidget(self.overview, 1, 1)

        if self.image.shape[1] == 1:
            self.imageScenes[1].setVisible(False)
            self.imageScenes[2].setVisible(False)
            self.overview.setVisible(False)

        self.gridWidget = QtGui.QWidget()
        self.gridWidget.setLayout(self.grid)
        self.layout.addWidget(self.gridWidget)

        #right side toolbox
        self.toolBox = QtGui.QWidget()
        self.toolBoxLayout = QtGui.QVBoxLayout()
        self.toolBox.setLayout(self.toolBoxLayout)
        self.toolBox.setMaximumWidth(150)
        self.toolBox.setMinimumWidth(150)


        #Label selector
        self.addLabelButton = QtGui.QPushButton("Create Label Class")
        self.connect(self.addLabelButton, QtCore.SIGNAL("pressed()"), self.addLabel)
        self.toolBoxLayout.addWidget(self.addLabelButton)

        self.labelAlphaSlider = QtGui.QSlider(QtCore.Qt.Horizontal, self)
        self.labelAlphaSlider.setRange(0,20)
        self.labelAlphaSlider.setValue(20)
        self.labelAlphaSlider.setToolTip('Change Label Opacity')
        self.connect(self.labelAlphaSlider, QtCore.SIGNAL('valueChanged(int)'), self.setLabelsAlpha)
        self.toolBoxLayout.addWidget( self.labelAlphaSlider)

        self.labelView = LabelListWidget(self)
        self.labelView.setSelectionMode(QtGui.QAbstractItemView.SingleSelection)
        self.connect(self.labelView.selectionModel(), QtCore.SIGNAL("selectionChanged(QItemSelection, QItemSelection)"), self.onLabelSelected)
        #only initialize after we have made the necessary connections
        self.labelView.initFromMgr(self.labels)

        self.toolBoxLayout.addWidget( self.labelView)


        if self.embedded == False:
            #Link to ComboBox
            self.editor_list.append(self)
            self.connect(self.editor_list, QtCore.SIGNAL("appended(int)"), self.linkComboAppend)
            self.connect(self.editor_list, QtCore.SIGNAL("removed(int)"), self.linkComboRemove)
    
            self.linkCombo = QtGui.QComboBox()
            self.linkCombo.setEnabled(True)
            self.linkCombo.addItem("None")
            for index, item in enumerate(self.editor_list.editors):
                self.linkCombo.addItem(item.name)
            self.connect(self.linkCombo, QtCore.SIGNAL("currentIndexChanged(int)"), self.linkToOther)
            self.toolBoxLayout.addWidget(QtGui.QLabel("Link to:"))
            self.toolBoxLayout.addWidget(self.linkCombo)

        self.toolBoxLayout.addSpacing(30)

        #Slice Selector Combo Box in right side toolbox
        self.sliceSelectors = []
        sliceSpin = QtGui.QSpinBox()
        sliceSpin.setEnabled(True)
        self.connect(sliceSpin, QtCore.SIGNAL("valueChanged(int)"), self.changeSliceX)
        if self.image.shape[2] > 1 and self.image.shape[3] > 1: #only show when needed
            tempLay = QtGui.QHBoxLayout()
            tempLay.addWidget(QtGui.QLabel("<pre>X:</pre>"))
            tempLay.addWidget(sliceSpin, 1)
            self.toolBoxLayout.addLayout(tempLay)
        sliceSpin.setRange(0,self.image.shape[1] - 1)
        self.sliceSelectors.append(sliceSpin)
        

        sliceSpin = QtGui.QSpinBox()
        sliceSpin.setEnabled(True)
        self.connect(sliceSpin, QtCore.SIGNAL("valueChanged(int)"), self.changeSliceY)
        if self.image.shape[1] > 1 and self.image.shape[3] > 1: #only show when needed
            tempLay = QtGui.QHBoxLayout()
            tempLay.addWidget(QtGui.QLabel("<pre>Y:</pre>"))
            tempLay.addWidget(sliceSpin, 1)
            self.toolBoxLayout.addLayout(tempLay)
        sliceSpin.setRange(0,self.image.shape[2] - 1)
        self.sliceSelectors.append(sliceSpin)

        sliceSpin = QtGui.QSpinBox()
        sliceSpin.setEnabled(True)
        self.connect(sliceSpin, QtCore.SIGNAL("valueChanged(int)"), self.changeSliceZ)
        if self.image.shape[1] > 1 and self.image.shape[2] > 1 : #only show when needed
            tempLay = QtGui.QHBoxLayout()
            tempLay.addWidget(QtGui.QLabel("<pre>Z:</pre>"))
            tempLay.addWidget(sliceSpin, 1)
            self.toolBoxLayout.addLayout(tempLay)
        sliceSpin.setRange(0,self.image.shape[3] - 1)
        self.sliceSelectors.append(sliceSpin)


        self.selSlices = []
        self.selSlices.append(0)
        self.selSlices.append(0)
        self.selSlices.append(0)
        
        #Channel Selector Combo Box in right side toolbox
        self.channelSpin = QtGui.QSpinBox()
        self.channelSpin.setEnabled(True)
        self.connect(self.channelSpin, QtCore.SIGNAL("valueChanged(int)"), self.setChannel)
        self.channelSpinLabel = QtGui.QLabel("Channel:")
        self.toolBoxLayout.addWidget(self.channelSpinLabel)
        self.toolBoxLayout.addWidget(self.channelSpin)
        if self.image.shape[-1] == 1 or self.image.rgb is True: #only show when needed
            self.channelSpin.setVisible(False)
            self.channelSpinLabel.setVisible(False)
        self.channelSpin.setRange(0,self.image.shape[-1] - 1)

        if self.embedded == False:
            self.addOverlayButton = QtGui.QPushButton("Add Overlay")
            self.connect(self.addOverlayButton, QtCore.SIGNAL("pressed()"), self.addOverlayDialog)
            self.toolBoxLayout.addWidget(self.addOverlayButton)
        else:
            self.toolBoxLayout.addWidget(QtGui.QLabel("Overlays:"))



        #Overlay selector
        self.overlayView = OverlayListWidget(self)
        self.toolBoxLayout.addWidget( self.overlayView)
        self.toolBoxLayout.addStretch()


        self.toolBoxLayout.setAlignment( QtCore.Qt.AlignTop )

        self.layout.addWidget(self.toolBox)

        # Make the dialog act as a window and stay on top
        if self.embedded == False:
            pass
            #self.setWindowFlags(self.flags() | QtCore.Qt.Window | QtCore.Qt.WindowStaysOnTopHint)

        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)

        #self.setWindowIcon(get_icon('edit.png'))
        self.setWindowTitle(self.tr("Volume") + \
                            "%s" % (" - "+str(title) if str(title) else ""))

        #start viewing in the center of the volume
        self.changeSliceX(numpy.floor((self.image.shape[1] - 1) / 2))
        self.changeSliceY(numpy.floor((self.image.shape[2] - 1) / 2))
        self.changeSliceZ(numpy.floor((self.image.shape[3] - 1) / 2))

        ##undo/redo and other shortcuts
        self.shortcutUndo = QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Z"), self, self.historyUndo, self.historyUndo) 
        shortcutManager.register(self.shortcutUndo, "history undo")
        
        self.shortcutRedo = QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Shift+Z"), self, self.historyRedo, self.historyRedo)
        shortcutManager.register(self.shortcutRedo, "history redo")
        
        self.shortcutRedo2 = QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Y"), self, self.historyRedo, self.historyRedo)
        shortcutManager.register(self.shortcutRedo2, "history redo")
        
        self.togglePredictionSC = QtGui.QShortcut(QtGui.QKeySequence("Space"), self, self.togglePrediction, self.togglePrediction)
        shortcutManager.register(self.togglePredictionSC, "toggle prediction overlays")
        
        self.shortcutNextLabel = QtGui.QShortcut(QtGui.QKeySequence("l"), self, self.nextLabel, self.nextLabel)
        shortcutManager.register(self.shortcutNextLabel, "go to next label (cyclic, forward)")
        
        self.shortcutPrevLabel = QtGui.QShortcut(QtGui.QKeySequence("k"), self, self.prevLabel, self.prevLabel)
        shortcutManager.register(self.shortcutPrevLabel, "go to previous label (cyclic, backwards)")
        
        self.shortcutToggleFullscreenX = QtGui.QShortcut(QtGui.QKeySequence("x"), self, self.toggleFullscreenX, self.toggleFullscreenX)
        shortcutManager.register(self.shortcutToggleFullscreenX, "enlarge slice view x to full size")
        
        self.shortcutToggleFullscreenY = QtGui.QShortcut(QtGui.QKeySequence("y"), self, self.toggleFullscreenY, self.toggleFullscreenY)
        shortcutManager.register(self.shortcutToggleFullscreenY, "enlarge slice view y to full size")
        
        self.shortcutToggleFullscreenZ = QtGui.QShortcut(QtGui.QKeySequence("z"), self, self.toggleFullscreenZ, self.toggleFullscreenZ)
        shortcutManager.register(self.shortcutToggleFullscreenZ, "enlarge slice view z to full size")
        
        self.shortcutUndo.setContext(QtCore.Qt.ApplicationShortcut )
        self.shortcutRedo.setContext(QtCore.Qt.ApplicationShortcut )
        self.shortcutRedo2.setContext(QtCore.Qt.ApplicationShortcut )
        self.togglePredictionSC.setContext(QtCore.Qt.ApplicationShortcut)
        self.shortcutPrevLabel.setContext(QtCore.Qt.ApplicationShortcut)
        self.shortcutNextLabel.setContext(QtCore.Qt.ApplicationShortcut)
        self.shortcutToggleFullscreenX.setContext(QtCore.Qt.ApplicationShortcut)
        self.shortcutToggleFullscreenY.setContext(QtCore.Qt.ApplicationShortcut)
        self.shortcutToggleFullscreenZ.setContext(QtCore.Qt.ApplicationShortcut)
        
        self.shortcutUndo.setEnabled(True)
        self.shortcutRedo.setEnabled(True)
        self.shortcutRedo2.setEnabled(True)
        self.togglePredictionSC.setEnabled(True)
        
        self.connect(self, QtCore.SIGNAL("destroyed()"),self.cleanUp)
        
        self.focusAxis =  0

    def toggleFullscreenX(self):
        self.maximizeSliceView(0, self.imageScenes[1].isVisible())
    
    def toggleFullscreenY(self):
        self.maximizeSliceView(1, self.imageScenes[0].isVisible())
        
    def toggleFullscreenZ(self):
        self.maximizeSliceView(2, self.imageScenes[1].isVisible())

    def maximizeSliceView(self, axis, maximize):
        a = range(3)
        if maximize:
            for i in a:
                self.imageScenes[i].setVisible(i == axis)
        else:
            for i in range(3):
                self.imageScenes[i].setVisible(True)
        
        self.imageScenes[axis].setFocus()
    
    def nextLabel(self):
        print "next label"
        i = self.labelView.selectedIndexes()[0].row()
        if i+1 == self.labelView.model().rowCount():
            i = self.labelView.model().index(0,0)
        else:
            i = self.labelView.model().index(i+1,0)
        self.labelView.selectionModel().setCurrentIndex(i, QtGui.QItemSelectionModel.ClearAndSelect)

    def prevLabel(self):
        print "prev label"
        i = self.labelView.selectedIndexes()[0].row()
        if i >  0:
            i = self.labelView.model().index(i-1,0)
        else:
            i = self.labelView.model().index(self.labelView.model().rowCount()-1,0)
        self.labelView.selectionModel().setCurrentIndex(i, QtGui.QItemSelectionModel.ClearAndSelect)

    def onLabelSelected(self, index):
        if self.labelView.currentItem() is not None:
            self.drawManager.setBrushColor(self.labelView.currentItem().color)
            for i in range(3):
                self.imageScenes[i].crossHairCursor.setColor(self.labelView.currentItem().color)

    def focusNextPrevChild(self, forward = True):
        if forward is True:
            self.focusAxis += 1
            if self.focusAxis > 2:
                self.focusAxis = 0
        else:
            self.focusAxis -= 1
            if self.focusAxis < 0:
                self.focusAxis = 2
        self.imageScenes[self.focusAxis].setFocus()
        return True
        

    def cleanUp(self):
        pass
#        for i, item in enumerate(self.imageScenes):
#            item.deleteLater()

    def togglePrediction(self):
        labelNames = self.labels.getLabelNames()
        state = None
        for index in range(0,self.overlayView.count()):
            item = self.overlayView.item(index)
            if str(item.text()) in labelNames:
                if state is None:
                   state = not(item.visible)
                item.visible = state
                item.setCheckState(item.visible * 2)
        self.repaint()
        

    def setLabelsAlpha(self, num):
        self.labelsAlpha = num / 20.0
        self.repaint()
        
    def getPendingLabels(self):
        temp = self.pendingLabels
        self.pendingLabels = []
        return temp

    def historyUndo(self):
        self.history.undo()

    def historyRedo(self):
        self.history.redo()

    def clearOverlays(self):
        self.overlayView.clearOverlays()

    def addOverlay(self, visible, data, name, color, alpha, colorTab = None):
        ov = VolumeOverlay(data,name, color, alpha, colorTab, visible)
        self.overlayView.addOverlay(ov)

    def addOverlayObject(self, ov):
        self.overlayView.addOverlay(ov)
        
    def addOverlayDialog(self):
        overlays = []
        for index, item in enumerate(self.editor_list.editors):
            overlays.append(item.name)
        itemName, ok  = QtGui.QInputDialog.getItem(self,"Add Overlay", "Overlay:", overlays, 0, False)
        if ok is True:
            for index, item in enumerate(self.editor_list.editors):
                if item.name == itemName:
                    ov = VolumeOverlay(item.image, item.name)
                    self.overlayView.addOverlay(ov)
        self.repaint()

    def repaint(self):
        for i in range(3):
            tempImage = None
            tempLabels = None
            tempoverlays = []   
            for index, item in enumerate(self.overlayView.overlays):
                if item.visible:
                    tempoverlays.append(item.getOverlaySlice(self.selSlices[i],i, self.selectedTime, 0)) 
    
            tempImage = self.image.getSlice(self.selSlices[i], i, self.selectedTime, self.selectedChannel)
    
            if self.labels.data is not None:
                tempLabels = self.labels.data.getSlice(self.selSlices[i],i, self.selectedTime, 0)
    
            self.imageScenes[i].displayNewSlice(tempImage, tempoverlays, tempLabels, self.labelsAlpha, fastPreview = False)


    def addLabel(self):
        self.labelView.createLabel()


    def get_copy(self):
        """Return modified text"""
        return unicode(self.edit.toPlainText())

    def setRgbMode(self, mode):
        """
        change display mode of 3-channel images to either rgb, or 3-channels
        mode can bei either  True or False
        """
        if self.image.shape[-1] == 3:
            self.image.rgb = mode
            self.channelSpin.setVisible(not mode)
            self.channelSpinLabel.setVisible(not mode)

    def setUseBorderMargin(self, use):
        self.useBorderMargin = use
        self.setBorderMargin(self.borderMargin)

    def setBorderMargin(self, margin):
        if self.useBorderMargin is True:
            if self.borderMargin != margin:
                print "new border margin:", margin
                self.borderMargin = margin
                self.imageScenes[0].__borderMarginIndicator__(margin)
                self.imageScenes[1].__borderMarginIndicator__(margin)
                self.imageScenes[2].__borderMarginIndicator__(margin)
                self.repaint()
        else:
                self.imageScenes[0].__borderMarginIndicator__(0)
                self.imageScenes[1].__borderMarginIndicator__(0)
                self.imageScenes[2].__borderMarginIndicator__(0)
                self.repaint()

    def changeSliceX(self, num):
        self.changeSlice(num, 0)

    def changeSliceY(self, num):
        self.changeSlice(num, 1)

    def changeSliceZ(self, num):
        self.changeSlice(num, 2)

    def setChannel(self, channel):
        self.selectedChannel = channel
        for i in range(3):
            self.changeSlice(self.selSlices[i], i)

    def setTime(self, time):
        self.selectedTime = time
        for i in range(3):
            self.changeSlice(self.selSlices[i], i)


    def changeSlice(self, num, axis):
        self.selSlices[axis] = num
        tempImage = None
        tempLabels = None
        tempoverlays = []
        self.sliceSelectors[axis].setValue(num)

        for index, item in enumerate(self.overlayView.overlays):
            if item.visible:
                tempoverlays.append(item.getOverlaySlice(num,axis, self.selectedTime, 0)) 

        tempImage = self.image.getSlice(num, axis, self.selectedTime, self.selectedChannel)


        if self.labels.data is not None:
            tempLabels = self.labels.data.getSlice(num,axis, self.selectedTime, 0)

        self.selSlices[axis] = num
        self.imageScenes[axis].sliceNumber = num
        self.imageScenes[axis].displayNewSlice(tempImage, tempoverlays, tempLabels, self.labelsAlpha, fastPreview = True)
        self.emit(QtCore.SIGNAL('changedSlice(int, int)'), num, axis)
#        for i in range(256):
#            col = QtGui.QColor(classColor.red(), classColor.green(), classColor.blue(), i * opasity)
#            image.setColor(i, col.rgba())

    def unlink(self):
        if self.linkedTo is not None:
            self.disconnect(self.editor_list.editors[self.linkedTo], QtCore.SIGNAL("changedSlice(int, int)"), self.changeSlice)
            self.linkedTo = None

    def linkToOther(self, index):
        self.unlink()
        if index > 0 and index != self.ownIndex + 1:
            other = self.editor_list.editors[index-1]
            self.connect(other, QtCore.SIGNAL("changedSlice(int, int)"), self.changeSlice)
            self.linkedTo = index - 1
        else:
            self.linkCombo.setCurrentIndex(0)

    def linkComboAppend(self, index):
        self.linkCombo.addItem( self.editor_list.editors[index].name )

    def linkComboRemove(self, index):
        if self.linkedTo == index:
            self.linkCombo.setCurrentIndex(0)
            self.linkedTo = None
        if self.linkedTo > index:
            self.linkedTo = self.linkedTo - 1
        if self.ownIndex > index:
            self.ownIndex = self.ownIndex - 1
            self.linkCombo.removeItem(index + 1)

    def closeEvent(self, event):
        self.disconnect(self.editor_list, QtCore.SIGNAL("appended(int)"), self.linkComboAppend)
        self.disconnect(self.editor_list, QtCore.SIGNAL("removed(int)"), self.linkComboRemove)
        self.unlink()
        self.editor_list.remove(self)
        event.accept()

    def wheelEvent(self, event):
        keys = QtGui.QApplication.keyboardModifiers()
        k_ctrl = (keys == QtCore.Qt.ControlModifier)
        
        if k_ctrl is True:        
            if event.delta() > 0:
                scaleFactor = 1.1
            else:
                scaleFactor = 0.9
            self.imageScenes[0].doScale(scaleFactor)
            self.imageScenes[1].doScale(scaleFactor)
            self.imageScenes[2].doScale(scaleFactor)

    def setLabels(self, offsets, axis, num, labels, erase):
        if axis == 0:
            offsets5 = (self.selectedTime,num,offsets[0],offsets[1],0)
            sizes5 = (1,1,labels.shape[0], labels.shape[1],1)
        elif axis == 1:
            offsets5 = (self.selectedTime,offsets[0],num,offsets[1],0)
            sizes5 = (1,labels.shape[0],1, labels.shape[1],1)
        else:
            offsets5 = (self.selectedTime,offsets[0],offsets[1],num,0)
            sizes5 = (1,labels.shape[0], labels.shape[1],1,1)
        
        vu = VolumeUpdate(labels.reshape(sizes5),offsets5, sizes5, erase)
        vu.applyTo(self.labels.data)
        self.pendingLabels.append(vu)

        patches = self.imageScenes[axis].patchAccessor.getPatchesForRect(offsets[0], offsets[1],offsets[0]+labels.shape[0], offsets[1]+labels.shape[1])

        tempImage = None
        tempLabels = None
        tempoverlays = []
        for index, item in enumerate(self.overlayView.overlays):
            if item.visible:
                tempoverlays.append(item.getOverlaySlice(self.selSlices[axis],axis, self.selectedTime, 0))

        tempImage = self.image.getSlice(self.selSlices[axis], axis, self.selectedTime, self.selectedChannel)

        if self.labels.data is not None:
            tempLabels = self.labels.data.getSlice(self.selSlices[axis],axis, self.selectedTime, 0)

        self.imageScenes[axis].updatePatches(patches, tempImage, tempoverlays, tempLabels, self.labelsAlpha)


        self.emit(QtCore.SIGNAL('newLabelsPending()'))
            
    def getVisibleState(self):
        #TODO: ugly, make nicer
        vs = [self.selectedTime, self.selSlices[0], self.selSlices[1], self.selSlices[2], self.selectedChannel]
        return vs



    def show(self):
        QtGui.QWidget.show(self)
        return  self.labels



class DrawManager(QtCore.QObject):
    def __init__(self, parent):
        QtCore.QObject.__init__(self)
        self.volumeEditor = parent
        self.shape = None
        self.brushSize = 3
        #self.initBoundingBox()
        self.penVis = QtGui.QPen(QtCore.Qt.white, 3, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin)
        self.penDraw = QtGui.QPen(QtCore.Qt.white, 3, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin)
        self.penDraw.setColor(QtCore.Qt.white)
        self.pos = None
        self.erasing = False
        self.lines = []
        self.scene = QtGui.QGraphicsScene()

    def copy(self):
        """
        make a shallow copy of DrawManager - needed for python 2.5 compatibility
        """
        cp = DrawManager(self.parent)
        cp.volumeEditor = self.volumeEditor
        cp.shape = self.shape
        cp.brushSize = self.brushSize
        cp.penVis = self.penVis
        cp.penDraw = self.penDraw
        cp.pos = self.pos
        cp.erasing = self.erasing
        cp.lines = self.lines
        cp.scene = self.scene
        return cp

    def initBoundingBox(self):
        self.leftMost = self.shape[0]
        self.rightMost = 0
        self.topMost = self.shape[1]
        self.bottomMost = 0

    def growBoundingBox(self):
        self.leftMost = max(0,self.leftMost - self.brushSize -1)
        self.topMost = max(0,self.topMost - self.brushSize -1 )
        self.rightMost = min(self.shape[0],self.rightMost + self.brushSize + 1)
        self.bottomMost = min(self.shape[1],self.bottomMost + self.brushSize + 1)

    def toggleErase(self):
        self.erasing = not(self.erasing)

    def setErasing(self):
        self.erasing = True
    
    def disableErasing(self):
        self.erasing = False

    def setBrushSize(self, size):
        for i in range(3):
            self.volumeEditor.imageScenes[i].crossHairCursor.setBrushSize(size)
        
        self.brushSize = size
        self.penVis.setWidth(size)
        self.penDraw.setWidth(size)
        
    def setBrushColor(self, color):
        self.penVis.setColor(color)
        
    def getCurrentPenPixmap(self):
        pixmap = QtGui.QPixmap(self.brushSize, self.brushSize)
        if self.erasing == True or not self.volumeEditor.labelView.currentItem():
            self.penVis.setColor(QtCore.Qt.black)
        else:
            self.penVis.setColor(self.volumeEditor.labelView.currentItem().color)
                    
        painter = QtGui.QPainter(pixmap)
        painter.setPen(self.penVis)
        painter.drawPoint(QtGui.Q)

    def beginDraw(self, pos, shape):
        self.shape = shape
        self.initBoundingBox()
        self.scene.clear()
        if self.erasing == True or not self.volumeEditor.labelView.currentItem():
            self.penVis.setColor(QtCore.Qt.black)
        else:
            self.penVis.setColor(self.volumeEditor.labelView.currentItem().color)
        self.pos = QtCore.QPoint(pos.x()+0.0001, pos.y()+0.0001)
        
        line = self.moveTo(pos)
        return line

    def endDraw(self, pos):
        self.moveTo(pos)
        self.growBoundingBox()

        tempi = QtGui.QImage(self.rightMost - self.leftMost, self.bottomMost - self.topMost, QtGui.QImage.Format_ARGB32_Premultiplied) #TODO: format
        tempi.fill(0)
        painter = QtGui.QPainter(tempi)
        
        self.scene.render(painter, QtCore.QRectF(0,0, self.rightMost - self.leftMost, self.bottomMost - self.topMost),
            QtCore.QRectF(self.leftMost, self.topMost, self.rightMost - self.leftMost, self.bottomMost - self.topMost))
        
        oldLeft = self.leftMost
        oldTop = self.topMost
        return (oldLeft, oldTop, tempi) #TODO: hackish, probably return a class ??

    def dumpDraw(self, pos):
        res = self.endDraw(pos)
        self.beginDraw(pos, self.shape)
        return res


    def moveTo(self, pos):      
        lineVis = QtGui.QGraphicsLineItem(self.pos.x(), self.pos.y(),pos.x(), pos.y())
        lineVis.setPen(self.penVis)
        
        line = QtGui.QGraphicsLineItem(self.pos.x(), self.pos.y(),pos.x(), pos.y())
        line.setPen(self.penDraw)
        self.scene.addItem(line)

        self.pos = pos
        x = pos.x()
        y = pos.y()
        #update bounding Box :
        if x > self.rightMost:
            self.rightMost = x
        if x < self.leftMost:
            self.leftMost = x
        if y > self.bottomMost:
            self.bottomMost = y
        if y < self.topMost:
            self.topMost = y
        return lineVis


    

class ImageSceneRenderThread(QtCore.QThread):
    def __init__(self, parent):
        QtCore.QThread.__init__(self, None)
        self.imageScene = parent
        self.patchAccessor = parent.patchAccessor
        self.volumeEditor = parent.volumeEditor
        #self.queue = deque(maxlen=1) #python 2.6
        self.queue = deque() #python 2.5

        self.dataPending = threading.Event()
        self.dataPending.clear()
        self.newerDataPending = threading.Event()
        self.newerDataPending.clear()
        self.stopped = False
        self.imagePatches = range(self.patchAccessor.patchCount)
            
    def run(self):
        #self.context.makeCurrent()

        while not self.stopped:
            self.dataPending.wait()
            self.newerDataPending.clear()
            while len(self.queue) > 0:
                stuff = self.queue.pop()
                if stuff is not None:
                    nums, origimage, overlays , origlabels , labelsAlpha, min, max  = stuff
                    for patchNr in nums:
                        if self.newerDataPending.isSet():
                            self.newerDataPending.clear()
                            break
                        bounds = self.patchAccessor.getPatchBounds(patchNr)

                        image = origimage[bounds[0]:bounds[1],bounds[2]:bounds[3]]

                        if image.dtype == 'uint16':
                            image = (image / 255).astype(numpy.uint8)

                        temp_image = qimage2ndarray.array2qimage(image.swapaxes(0,1), normalize=(min,max))

                        p = QtGui.QPainter(self.imageScene.scene.image)
                        p.translate(bounds[0],bounds[2])
                        #p = QtGui.QPainter(temp_image)
                        p.drawImage(0,0,temp_image)

                        #add overlays
                        for index, origitem in enumerate(overlays):
                            p.setOpacity(origitem.alpha)
                            itemcolorTable = origitem.colorTable
                            itemdata = origitem.data[bounds[0]:bounds[1],bounds[2]:bounds[3]]
                            if origitem.colorTable != None:
                                image0 = qimage2ndarray.gray2qimage(itemdata.swapaxes(0,1), normalize=False)
                                image0.setColorTable(origitem.colorTable)
                            else:
                                image0 = QtGui.QImage(itemdata.shape[0],itemdata.shape[1],QtGui.QImage.Format_ARGB32)#qimage2ndarray.array2qimage(itemdata.swapaxes(0,1), normalize=False)
                                image0.fill(origitem.color.rgba())
                                image0.setAlphaChannel(qimage2ndarray.gray2qimage(itemdata.swapaxes(0,1), False))

                            p.drawImage(0,0, image0)
                        if origlabels is not None:
                            labels = origlabels[bounds[0]:bounds[1],bounds[2]:bounds[3]]
                            #p.setOpacity(item.alpha)

                            p.setOpacity(labelsAlpha)
                            image0 = qimage2ndarray.gray2qimage(labels.swapaxes(0,1), False)

                            image0.setColorTable(self.volumeEditor.labelView.colorTab)
                            mask = image0.createMaskFromColor(QtGui.QColor(0,0,0).rgb(),QtCore.Qt.MaskOutColor)
                            image0.setAlphaChannel(mask)
                            p.drawImage(0,0, image0)

                        p.end()

                        #self.imagePatches[patchNr] = temp_image

#                        #draw the patch result to complete image
#                        p = QtGui.QPainter(self.imageScene.scene.image)
#                        p.drawImage(bounds[0],bounds[2],self.imagePatches[patchNr])
#                        p.end()

    #                    #this code would be cool, but unfortunately glTexSubimage doesnt work ??
    #                    glBindTexture(GL_TEXTURE_2D,self.imageScene.scene.tex)
    #                    pixels = qimage2ndarray.byte_view(temp_image)
    #                    print pixels.shape
    #                    glTexSubImage2D(GL_TEXTURE_2D,0,bounds[0],bounds[2],bounds[1]-bounds[0],bounds[3]-bounds[2],GL_RGBA,GL_UNSIGNED_BYTE, pixels )

                        #This signal is not needed anymore for now
                        #self.emit(QtCore.SIGNAL("finishedPatch(int)"),patchNr)
            self.dataPending.clear()
            self.emit(QtCore.SIGNAL('finishedQueue()'))

class CrossHairCursor(QtGui.QGraphicsItem) :
    modeYPosition  = 0
    modeXPosition  = 1
    modeXYPosition = 2
    
    def boundingRect(self):
        return QtCore.QRectF(0,0, self.width, self.height)
    def __init__(self, width, height):
        QtGui.QGraphicsItem.__init__(self)
        
        self.width = width
        self.height = height
        
        self.penDotted = QtGui.QPen(QtCore.Qt.red, 2, QtCore.Qt.DotLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin)
        self.penDotted.setCosmetic(True)
        
        self.penSolid = QtGui.QPen(QtCore.Qt.red, 2)
        self.penSolid.setCosmetic(True)
        
        self.x = 0
        self.y = 0
        self.brushSize = 0
        
        self.mode = self.modeXYPosition
    
    def setColor(self, color):
        self.penDotted = QtGui.QPen(color, 2, QtCore.Qt.DotLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin)
        self.penDotted.setCosmetic(True)
        self.penSolid  = QtGui.QPen(color, 2)
        self.penSolid.setCosmetic(True)
        self.update()
    
    def showXPosition(self, x):
        """only mark the x position by displaying a line f(y) = x"""
        self.setVisible(True)
        self.mode = self.modeXPosition
        self.setPos(x,0)
        
    def showYPosition(self, y):
        """only mark the y position by displaying a line f(x) = y"""
        self.setVisible(True)
        self.mode = self.modeYPosition
        self.setPos(0,y)
        
    def showXYPosition(self, x,y):
        """mark the (x,y) position by displaying a cross hair cursor
           including a circle indicating the current brush size"""
        self.setVisible(True)
        self.mode = self.modeXYPosition
        self.setPos(x,y)
    
    def paint(self, painter, option, widget=None):
        painter.setPen(self.penDotted)
        
        if self.mode == self.modeXPosition:
            painter.drawLine(self.x, 0, self.x, self.height)
        elif self.mode == self.modeYPosition:
            painter.drawLine(0, self.y, self.width, self.y)
        else:
            painter.drawLine(0,                         self.y, self.x-0.5*self.brushSize, self.y)
            painter.drawLine(self.x+0.5*self.brushSize, self.y, self.width,                self.y)

            painter.drawLine(self.x, 0,                         self.x, self.y-0.5*self.brushSize)
            painter.drawLine(self.x, self.y+0.5*self.brushSize, self.x, self.height)

            painter.setPen(self.penSolid)
            painter.drawEllipse(self.x-0.5*self.brushSize, self.y-0.5*self.brushSize, 1*self.brushSize, 1*self.brushSize)
        
    def setPos(self, x, y):
        self.x = x
        self.y = y
        self.update()
        
    def setBrushSize(self, size):
        self.brushSize = size
        self.update()

class ImageGraphicsItem(QtGui.QGraphicsItem):
    def __init__(self, image):
        QtGui.QGraphicsItem.__init__(self)
        self.image = image

    def paint(self,painter, options, widget):
        painter.setClipRect( options.exposedRect )
        painter.drawImage(0,0,self.image)

    def boundingRect(self):
        return QtCore.QRectF(self.image.rect())


class CustomGraphicsScene( QtGui.QGraphicsScene):#, QtOpenGL.QGLWidget):
    def __init__(self,parent,widget,image):
        QtGui.QGraphicsScene.__init__(self)
        #QtOpenGL.QGLWidget.__init__(self)
        self.widget = widget
        self.imageScene = parent
        self.image = image
        self.bgColor = QtGui.QColor(QtCore.Qt.black)
        self.tex = -1

            
    def drawBackground(self, painter, rect):
        #painter.fillRect(rect,self.bgBrush)
        if self.widget != None:

            self.widget.context().makeCurrent()
            
            glClearColor(self.bgColor.redF(),self.bgColor.greenF(),self.bgColor.blueF(),1.0)
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

            if self.tex > -1:
                #self.widget.drawTexture(QtCore.QRectF(self.image.rect()),self.tex)
                d = painter.device()
                dc = sip.cast(d,QtOpenGL.QGLFramebufferObject)

                rect = QtCore.QRectF(self.image.rect())
                
                #switch corrdinates if qt version is small
                painter.beginNativePainting()
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
                dc.drawTexture(rect,self.tex)
                painter.endNativePainting()

#            rect = rect.intersected(QtCore.QRectF(self.image.rect()))
#
#            patches =  self.imageScene.patchAccessor.getPatchesForRect(rect.x(),rect.y(),rect.x()+rect.width(),rect.y()+rect.height())
#            #print self.imageScene.patchAccessor.patchCount
#            #print patches
#            for i in patches:
#                bounds = self.imageScene.patchAccessor.getPatchBounds(i)
#                if self.imageScene.textures[i] >= 0:
#                    self.widget.drawTexture(QtCore.QRectF(QtCore.QRect(bounds[0],bounds[2],bounds[1]-bounds[0],bounds[3]-bounds[2])), self.imageScene.textures[i] )

        else:
            painter.setClipRect(rect)
            painter.drawImage(0,0,self.image)
        



class ImageScene( QtGui.QGraphicsView):
    def __borderMarginIndicator__(self, margin):
        """
        update the border margin indicator (left, right, top, bottom)
        to reflect the new given margin
        """
        self.margin = margin
        if self.border:
            self.scene.removeItem(self.border)
        borderPath = QtGui.QPainterPath()
        borderPath.setFillRule(QtCore.Qt.WindingFill)
        borderPath.addRect(0,0, margin, self.imShape[1])
        borderPath.addRect(0,0, self.imShape[0], margin)
        borderPath.addRect(self.imShape[0]-margin,0, margin, self.imShape[1])
        borderPath.addRect(0,self.imShape[1]-margin, self.imShape[0], margin)
        self.border = QtGui.QGraphicsPathItem(borderPath)
        brush = QtGui.QBrush(QtGui.QColor(0,0,255))
        brush.setStyle( QtCore.Qt.Dense7Pattern )
        self.border.setBrush(brush)
        self.border.setPen(QtGui.QPen(QtCore.Qt.NoPen))
        self.border.setZValue(200)
        self.scene.addItem(self.border)
        
    def __init__(self, parent, imShape, axis, drawManager):
        """
        imShape: 3D shape of the block that this slice view displays.
                 first two entries denote the x,y extent of one slice,
                 the last entry is the extent in slice direction
        """
        QtGui.QGraphicsView.__init__(self)
        self.imShape = imShape[0:2]
        self.drawManager = drawManager
        self.tempImageItems = []
        self.volumeEditor = parent
        self.axis = axis
        self.sliceNumber = 0
        self.sliceExtent = imShape[2]
        self.drawing = False
        self.view = self
        self.image = QtGui.QImage(imShape[0], imShape[1], QtGui.QImage.Format_ARGB32)
        self.border = None
        self.allBorder = None

	self.min = 0
	self.max = 255

        self.openglWidget = None
        ##enable OpenGL acceleratino
        if self.volumeEditor.opengl is True:
            self.openglWidget = QtOpenGL.QGLWidget()
            self.setViewport(self.openglWidget)
            self.setViewportUpdateMode(QtGui.QGraphicsView.FullViewportUpdate)


        self.scene = CustomGraphicsScene(self, self.openglWidget, self.image)
        self.view.setScene(self.scene)
        self.scene.setSceneRect(0,0, imShape[0],imShape[1])
        self.view.setSceneRect(0,0, imShape[0],imShape[1])
        self.scene.bgColor = QtGui.QColor(QtCore.Qt.white)
        if os.path.isfile('gui/backGroundBrush.png'):
            self.scene.bgBrush = QtGui.QBrush(QtGui.QImage('gui/backGroundBrush.png'))
        else:
            self.scene.bgBrush = QtGui.QBrush(QtGui.QColor(QtCore.Qt.black))
        #self.setBackgroundBrush(brushImage)
        self.view.setRenderHint(QtGui.QPainter.Antialiasing, False)
        #self.view.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, False)

        self.patchAccessor = PatchAccessor(imShape[0],imShape[1],64)
        print "PatchCount :", self.patchAccessor.patchCount
        self.imagePatchItems = []
        self.pixmapPatches = []
        self.textures = []
        for i in range(self.patchAccessor.patchCount + 1):
            self.imagePatchItems.append(None)
            self.pixmapPatches.append(None)
            self.textures.append(-1)

        self.pixmap = QtGui.QPixmap.fromImage(self.image)
        self.imageItem = QtGui.QGraphicsPixmapItem(self.pixmap)
        
        if self.axis is 0:
            self.setStyleSheet("QWidget:!focus { border: 2px solid red; border-radius: 4px; }\
                                QWidget:focus { border: 2px solid white; border-radius: 4px; }")
            self.view.rotate(90.0)
            self.view.scale(1.0,-1.0)
        if self.axis is 1:
            self.setStyleSheet("QWidget:!focus { border: 2px solid green; border-radius: 4px; } \
                                QWidget:focus { border: 2px solid white; border-radius: 4px; }")
        if self.axis is 2:
            self.setStyleSheet("QWidget:!focus { border: 2px solid blue; border-radius: 4px; } \
                                QWidget:focus { border: 2px solid white; border-radius: 4px; }")
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.connect(self, QtCore.SIGNAL("customContextMenuRequested(QPoint)"), self.onContext)

        self.setMouseTracking(True)

        #indicators for the biggest filter mask's size
        #marks the area where labels should not be placed
        # -> the margin top, left, right, bottom
        self.__borderMarginIndicator__(0)
        # -> the complete 2D slice is marked
        brush = QtGui.QBrush(QtGui.QColor(0,0,255))
        brush.setStyle( QtCore.Qt.DiagCrossPattern )
        allBorderPath = QtGui.QPainterPath()
        allBorderPath.setFillRule(QtCore.Qt.WindingFill)
        allBorderPath.addRect(0, 0, imShape[0], imShape[1])
        self.allBorder = QtGui.QGraphicsPathItem(allBorderPath)
        self.allBorder.setBrush(brush)
        self.allBorder.setPen(QtGui.QPen(QtCore.Qt.NoPen))
        self.scene.addItem(self.allBorder)
        self.allBorder.setVisible(False)
        self.allBorder.setZValue(99)

        #label updates while drawing, needed for interactive segmentation
        self.drawTimer = QtCore.QTimer()
        self.connect(self.drawTimer, QtCore.SIGNAL("timeout()"), self.updateLabels)
        
        # invisible cursor to enable custom cursor
        self.hiddenCursor = QtGui.QCursor(QtCore.Qt.BlankCursor)
        
        # For screen recording BlankCursor dont work
        #self.hiddenCursor = QtGui.QCursor(QtCore.Qt.ArrowCursor)
        
        self.thread = ImageSceneRenderThread(self)
        self.connect(self.thread, QtCore.SIGNAL('finishedPatch(int)'),self.redrawPatch)
        self.connect(self.thread, QtCore.SIGNAL('finishedQueue()'), self.clearTempitems)
        self.thread.start()
        
        self.connect(self, QtCore.SIGNAL("destroyed()"),self.cleanUp)

        self.shortcutZoomIn = QtGui.QShortcut(QtGui.QKeySequence("+"), self, self.zoomIn, self.zoomIn)
        shortcutManager.register(self.shortcutZoomIn, "zoom in")
        self.shortcutZoomIn.setContext(QtCore.Qt.WidgetShortcut )

        self.shortcutZoomOut = QtGui.QShortcut(QtGui.QKeySequence("-"), self, self.zoomOut, self.zoomOut)
        shortcutManager.register(self.shortcutZoomOut, "zoom out")
        self.shortcutZoomOut.setContext(QtCore.Qt.WidgetShortcut )
        
        self.shortcutSliceUp = QtGui.QShortcut(QtGui.QKeySequence("p"), self, self.sliceUp, self.sliceUp)
        shortcutManager.register(self.shortcutSliceUp, "slice up")
        self.shortcutSliceUp.setContext(QtCore.Qt.WidgetShortcut )
        
        self.shortcutSliceDown = QtGui.QShortcut(QtGui.QKeySequence("o"), self, self.sliceDown, self.sliceDown)
        shortcutManager.register(self.shortcutSliceDown, "slice down")
        self.shortcutSliceDown.setContext(QtCore.Qt.WidgetShortcut )

        self.shortcutSliceUp2 = QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Up"), self, self.sliceUp, self.sliceUp)
        shortcutManager.register(self.shortcutSliceUp2, "slice up")
        self.shortcutSliceUp2.setContext(QtCore.Qt.WidgetShortcut )

        self.shortcutSliceDown2 = QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Down"), self, self.sliceDown, self.sliceDown)
        shortcutManager.register(self.shortcutSliceDown2, "slice down")
        self.shortcutSliceDown2.setContext(QtCore.Qt.WidgetShortcut )


        self.shortcutSliceUp10 = QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Shift+Up"), self, self.sliceUp10, self.sliceUp10)
        shortcutManager.register(self.shortcutSliceUp10, "10 slices up")
        self.shortcutSliceUp10.setContext(QtCore.Qt.WidgetShortcut )

        self.shortcutSliceDown10 = QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Shift+Down"), self, self.sliceDown10, self.sliceDown10)
        shortcutManager.register(self.shortcutSliceDown10, "10 slices down")
        self.shortcutSliceDown10.setContext(QtCore.Qt.WidgetShortcut )


        self.shortcutBrushSizeUp = QtGui.QShortcut(QtGui.QKeySequence("n"), self, self.brushSmaller, self.brushSmaller)
        shortcutManager.register(self.shortcutBrushSizeUp, "increase brush size")
        self.shortcutBrushSizeDown = QtGui.QShortcut(QtGui.QKeySequence("m"), self, self.brushBigger, self.brushBigger)
        shortcutManager.register(self.shortcutBrushSizeDown, "decrease brush size")
 
        self.crossHairCursor = CrossHairCursor(self.image.width(), self.image.height())
        self.crossHairCursor.setZValue(100)
        self.scene.addItem(self.crossHairCursor)

        self.tempErase = False

    def changeSlice(self, delta):
        if self.drawing == True:
            self.endDraw(self.mousePos)
            self.drawing = True
            self.drawManager.beginDraw(self.mousePos, self.imShape)

        self.volumeEditor.sliceSelectors[self.axis].stepBy(delta)


    def sliceUp(self):
        self.changeSlice(1)
        
    def sliceUp10(self):
        self.changeSlice(10)

    def sliceDown(self):
        self.changeSlice(-1)

    def sliceDown10(self):
        self.changeSlice(-10)


    def brushSmaller(self):
        b = self.drawManager.brushSize
        if b > 2:
            self.drawManager.setBrushSize(b-1)
            self.crossHairCursor.setBrushSize(b-1)
        
    def brushBigger(self):
        b = self.drawManager.brushSize
        if b < 20:
            self.drawManager.setBrushSize(b+1)
            self.crossHairCursor.setBrushSize(b+1)

    def cleanUp(self):
        #print "stopping ImageSCeneRenderThread", str(self.axis)
        
        self.thread.stopped = True
        self.thread.dataPending.set()
        self.thread.wait()

    def updatePatches(self, patchNumbers ,image, overlays = [], labels = None, labelsAlpha = 1.0):
        stuff = [patchNumbers,image, overlays, labels, labelsAlpha, self.min, self.max]
        #print patchNumbers
        if patchNumbers is not None:
            self.thread.queue.append(stuff)
            self.thread.dataPending.set()

    def displayNewSlice(self, image, overlays = [], labels = None, labelsAlpha = 1.0, fastPreview = True):
        self.thread.queue.clear()
        self.thread.newerDataPending.set()

        #if we are in opengl 2d render mode, quickly update the texture without any overlays
        #to get a fast update on slice change
        if fastPreview is True and self.openglWidget is not None and len(image.shape) == 2:
            self.openglWidget.context().makeCurrent()
            t = self.scene.tex
            self.scene.tex = -1
            if t > -1:
                self.openglWidget.deleteTexture(t)
            ti = qimage2ndarray.gray2qimage(image.swapaxes(0,1), normalize = self.volumeEditor.normalizeData)
            self.scene.tex = self.openglWidget.bindTexture(ti, GL_TEXTURE_2D, GL_RGB)
            self.viewport().repaint()

        if self.volumeEditor.normalizeData:
            self.min = numpy.min(image)
            self.max = numpy.max(image)
        else:
            self.min = 0
            self.max = 255

            self.updatePatches(range(self.patchAccessor.patchCount),image, overlays, labels, labelsAlpha)

    def display(self, image, overlays = [], labels = None, labelsAlpha = 1.0):
        self.thread.queue.clear()
        self.updatePatches(range(self.patchAccessor.patchCount),image, overlays, labels, labelsAlpha)

    def clearTempitems(self):
        #only proceed if htere is no new data already in the rendering thread queue
        if not self.thread.dataPending.isSet():
            #if, in slicing direction, we are within the margin of the image border
            #we set the border overlay indicator to visible
            self.allBorder.setVisible((self.sliceNumber < self.margin or self.sliceExtent - self.sliceNumber < self.margin) and self.sliceExtent > 1)

            #if we are in opengl 2d render mode, update the texture
            if self.openglWidget is not None:
                self.openglWidget.context().makeCurrent()
                t = self.scene.tex
                self.scene.tex = -1
                if t > -1:
                    self.openglWidget.deleteTexture(t)
                self.scene.tex = self.openglWidget.bindTexture(self.scene.image, GL_TEXTURE_2D, GL_RGBA)

            #if all updates have been rendered remove tempitems
            if self.thread.queue.__len__() == 0:
                for index, item in enumerate(self.tempImageItems):
                    self.scene.removeItem(item)
                self.tempImageItems = []

            #update the scene, and the 3d overvie
        #print "updating slice view ", self.axis
        self.viewport().repaint() #update(QtCore.QRectF(self.image.rect()))
        self.volumeEditor.overview.display(self.axis)
        
    def redrawPatch(self, patchNr):
        if self.thread.stopped is False:
            pass
#            patch = self.thread.imagePatches[patchNr]
#            if self.textures[patchNr] < 0 :
#                t = self.openglWidget.bindTexture(patch)
#                self.textures[patchNr] = t
#            else:
#                t_old = self.textures[patchNr]
#
#                t_new = self.openglWidget.bindTexture(patch)
#                self.textures[patchNr] = t_new
#
#                self.openglWidget.deleteTexture(t_old)

#            bounds = self.patchAccessor.getPatchBounds(patchNr)
#            p = QtGui.QPainter(self.scene.image)
#            p.drawImage(bounds[0],bounds[2],self.thread.imagePatches[patchNr])
#            p.end()

            #self.scene.update(bounds[0],bounds[2],bounds[1]-bounds[0],bounds[3]-bounds[2])
        
    def updateLabels(self):
        result = self.drawManager.dumpDraw(self.mousePos)
        image = result[2]
        ndarr = qimage2ndarray.rgb_view(image)
        labels = ndarr[:,:,0]
        labels = labels.swapaxes(0,1)
        number = self.volumeEditor.labelView.currentItem().number
        labels = numpy.where(labels > 0, number, 0)
        ls = LabelState('drawing', self.axis, self.volumeEditor.selSlices[self.axis], result[0:2], labels.shape, self.volumeEditor.selectedTime, self.volumeEditor, self.drawManager.erasing, labels, number)
        self.volumeEditor.history.append(ls)        
        self.volumeEditor.setLabels(result[0:2], self.axis, self.volumeEditor.sliceSelectors[self.axis].value(), labels, self.drawManager.erasing)

    
    def beginDraw(self, pos):
        self.mousePos = pos
        self.drawing  = True
        line = self.drawManager.beginDraw(pos, self.imShape)
        line.setZValue(99)
        self.tempImageItems.append(line)
        self.scene.addItem(line)

        if self.volumeEditor.drawUpdateInterval > 0:
            self.drawTimer.start(self.volumeEditor.drawUpdateInterval) #update labels every some ms
        
    def endDraw(self, pos):
        self.drawTimer.stop()
        result = self.drawManager.endDraw(pos)
        image = result[2]
        ndarr = qimage2ndarray.rgb_view(image)
        labels = ndarr[:,:,0]
        labels = labels.swapaxes(0,1)
        number = self.volumeEditor.labelView.currentItem().number
        labels = numpy.where(labels > 0, number, 0)
        ls = LabelState('drawing', self.axis, self.volumeEditor.selSlices[self.axis], result[0:2], labels.shape, self.volumeEditor.selectedTime, self.volumeEditor, self.drawManager.erasing, labels, number)
        self.volumeEditor.history.append(ls)        
        self.volumeEditor.setLabels(result[0:2], self.axis, self.volumeEditor.sliceSelectors[self.axis].value(), labels, self.drawManager.erasing)
        self.drawing = False


    def wheelEvent(self, event):
        keys = QtGui.QApplication.keyboardModifiers()
        k_alt = (keys == QtCore.Qt.AltModifier)
        k_ctrl = (keys == QtCore.Qt.ControlModifier)

        self.mousePos = self.mapToScene(event.pos())

        if event.delta() > 0:
            if k_alt is True:
                self.changeSlice(10)
            elif k_ctrl is True:
                scaleFactor = 1.1
                self.doScale(scaleFactor)
            else:
                self.changeSlice(1)
        else:
            if k_alt is True:
                self.changeSlice(-10)
            elif k_ctrl is True:
                scaleFactor = 0.9
                self.doScale(scaleFactor)
            else:
                self.changeSlice(-1)

    def zoomOut(self):
        self.doScale(0.9)

    def zoomIn(self):
        self.doScale(1.1)

    def doScale(self, factor):
        self.view.scale(factor, factor)


    def tabletEvent(self, event):
        self.setFocus(True)
        
        if not self.volumeEditor.labelView.currentItem():
            return
        
        self.mousePos = mousePos = self.mapToScene(event.pos())
        
        x = mousePos.x()
        y = mousePos.y()
        if event.pointerType() == QtGui.QTabletEvent.Eraser or QtGui.QApplication.keyboardModifiers() == QtCore.Qt.ShiftModifier:
            self.drawManager.setErasing()
        elif event.pointerType() == QtGui.QTabletEvent.Pen and QtGui.QApplication.keyboardModifiers() != QtCore.Qt.ShiftModifier:
            self.drawManager.disableErasing()
        if self.drawing == True:
            if event.pressure() == 0:
                self.endDraw(mousePos)
                self.volumeEditor.changeSlice(self.volumeEditor.selSlices[self.axis], self.axis)
            else:
                if self.drawManager.erasing:
                    #make the brush size bigger while erasing
                    self.drawManager.setBrushSize(int(event.pressure()*10))
                else:
                    self.drawManager.setBrushSize(int(event.pressure()*7))
        if self.drawing == False:
            if event.pressure() > 0:
                self.beginDraw(mousePos)
                
                
        self.mouseMoveEvent(event)


    def mousePressEvent(self, event):
        if not self.volumeEditor.labelView.currentItem():
            return
        
        if event.buttons() == QtCore.Qt.LeftButton:
            if QtGui.QApplication.keyboardModifiers() == QtCore.Qt.ShiftModifier:
                self.drawManager.setErasing()
                self.tempErase = True
            mousePos = self.mapToScene(event.pos())
            self.beginDraw(mousePos)
        elif event.buttons() == QtCore.Qt.RightButton:
            self.onContext(event.pos())

    def mouseReleaseEvent(self, event):
        if self.drawing == True:
            mousePos = self.mapToScene(event.pos())
            self.endDraw(mousePos)
        if self.tempErase == True:
            self.drawManager.disableErasing()
            self.tempErase = False
            
    def mouseMoveEvent(self,event):
        self.mousePos = mousePos = self.mousePos = self.mapToScene(event.pos())
        x = mousePos.x()
        y = mousePos.y()

        if x > 0 and x < self.image.width() and y > 0 and y < self.image.height():
            #should we hide the cursor only when entering once ? performance?
            self.setCursor(self.hiddenCursor)
            
            self.crossHairCursor.showXYPosition(x,y)
            #self.crossHairCursor.setPos(x,y)
            
            if self.axis == 0:
                yView = self.volumeEditor.imageScenes[1].crossHairCursor
                zView = self.volumeEditor.imageScenes[2].crossHairCursor
                
                yView.setVisible(False)
                zView.showYPosition(x)
                
            elif self.axis == 1:
                xView = self.volumeEditor.imageScenes[0].crossHairCursor
                zView = self.volumeEditor.imageScenes[2].crossHairCursor
                
                zView.showXPosition(x)
                xView.setVisible(False)
            else:
                xView = self.volumeEditor.imageScenes[0].crossHairCursor
                yView = self.volumeEditor.imageScenes[1].crossHairCursor
                
                xView.showXPosition(y)
                yView.showXPosition(x)
        else:
            self.unsetCursor()
                
        
        if self.drawing == True:
            line = self.drawManager.moveTo(mousePos)
            line.setZValue(99)
            self.tempImageItems.append(line)
            self.scene.addItem(line)


    def mouseDoubleClickEvent(self, event):
        mousePos = self.mapToScene(event.pos())
        x = mousePos.x()
        y = mousePos.y()
        
          
        if self.axis == 0:
            self.volumeEditor.changeSlice(x, 1)
            self.volumeEditor.changeSlice(y, 2)
        elif self.axis == 1:
            self.volumeEditor.changeSlice(x, 0)
            self.volumeEditor.changeSlice(y, 2)
        elif self.axis ==2:
            self.volumeEditor.changeSlice(x, 0)
            self.volumeEditor.changeSlice(y, 1)

    def onContext(self, pos):
        menu = QtGui.QMenu(self)
        labeling = menu.addMenu("Labeling")
        toggleEraseA = None
        if self.drawManager.erasing == True:
            toggleEraseA = labeling.addAction("Enable Labelmode")
        else:
            toggleEraseA = labeling.addAction("Enable Eraser")
            
        brushM = labeling.addMenu("Brush size")
        brush1 = brushM.addAction("1")
        brush3 = brushM.addAction("3")
        brush5 = brushM.addAction("5")
        brush10 = brushM.addAction("10")

        action = menu.exec_(QtGui.QCursor.pos())
        if action == toggleEraseA:
            self.drawManager.toggleErase()
        elif action == brush1:
            self.drawManager.setBrushSize(1)
        elif action == brush3:
            self.drawManager.setBrushSize(3)
        elif action == brush5:
            self.drawManager.setBrushSize(5)
        elif action == brush10:
            self.drawManager.setBrushSize(10)


class OverviewSceneDummy(QtGui.QWidget):
    def __init__(self, parent, shape):
        QtGui.QWidget.__init__(self)
        pass
    
    def display(self, axis):
        pass

    def redisplay(self):
        pass
    
class OverviewScene(QtOpenGL.QGLWidget):
    def __init__(self, parent, shape):
        QtOpenGL.QGLWidget.__init__(self)
        self.sceneShape = shape
        self.volumeEditor = parent
        self.images = parent.imageScenes
        self.sceneItems = []
        self.initialized = False
        self.tex = []
        self.tex.append(-1)
        self.tex.append(-1)
        self.tex.append(-1)
        if self.volumeEditor.openglOverview is False:
            self.setVisible(False)

    def display(self, axis):
        if self.volumeEditor.openglOverview is True:  
            if self.initialized is True:
                #self.initializeGL()
                self.makeCurrent()
                if self.tex[axis] > -1:
                    self.deleteTexture(self.tex[axis])
                self.paintGL(axis)
                self.swapBuffers()
            
    def redisplay(self):
        if self.volumeEditor.openglOverview is True:
            if self.initialized is True:
                for i in range(3):
                    self.makeCurrent()
                    if self.tex[i] > -1:
                        self.deleteTexture(self.tex[i])
                    self.paintGL(i)
                self.swapBuffers()        

    def paintGL(self, axis = None):
        if self.volumeEditor.openglOverview is True:
            '''
            Drawing routine
            '''
            pix0 = self.images[0].pixmap
            pix1 = self.images[1].pixmap
            pix2 = self.images[2].pixmap
    
            maxi = max(pix0.width(),pix1.width())
            maxi = max(maxi, pix2.width())
            maxi = max(maxi, pix0.height())
            maxi = max(maxi, pix1.height())
            maxi = max(maxi, pix2.height())
    
            ratio0w = 1.0 * pix0.width() / maxi
            ratio1w = 1.0 * pix1.width() / maxi
            ratio2w = 1.0 * pix2.width() / maxi
    
            ratio0h = 1.0 * pix0.height() / maxi
            ratio1h = 1.0 * pix1.height() / maxi
            ratio2h = 1.0 * pix2.height() / maxi
           
            glMatrixMode(GL_MODELVIEW)
    
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
            glLoadIdentity()
    
            glRotatef(30,1.0,0.0,0.0)
    
            glTranslatef(0,-3,-5)        # Move Into The Screen
    
            glRotatef(-30,0.0,1.0,0.0)        # Rotate The Cube On X, Y & Z
    
            #glRotatef(180,1.0,0.0,1.0)        # Rotate The Cube On X, Y & Z
    
            glPolygonMode( GL_FRONT_AND_BACK, GL_LINE ) #wireframe mode
    
            glBegin(GL_QUADS)            # Start Drawing The Cube
    
            glColor3f(1.0,0.0,1.0)            # Set The Color To Violet
            
            glVertex3f( ratio2w, ratio1h,-ratio2h)        # Top Right Of The Quad (Top)
            glVertex3f(-ratio2w, ratio1h,-ratio2h)        # Top Left Of The Quad (Top)
            glVertex3f(-ratio2w, ratio1h, ratio2h)        # Bottom Left Of The Quad (Top)
            glVertex3f( ratio2w, ratio1h, ratio2h)        # Bottom Right Of The Quad (Top)
    
            glVertex3f( ratio2w,-ratio1h, ratio2h)        # Top Right Of The Quad (Bottom)
            glVertex3f(-ratio2w,-ratio1h, ratio2h)        # Top Left Of The Quad (Bottom)
            glVertex3f(-ratio2w,-ratio1h,-ratio2h)        # Bottom Left Of The Quad (Bottom)
            glVertex3f( ratio2w,-ratio1h,-ratio2h)        # Bottom Right Of The Quad (Bottom)
    
            glVertex3f( ratio2w, ratio1h, ratio2h)        # Top Right Of The Quad (Front)
            glVertex3f(-ratio2w, ratio1h, ratio2h)        # Top from PyQt4 import QtCore, QtGui, QtOpenGLLeft Of The Quad (Front)
            glVertex3f(-ratio2w,-ratio1h, ratio2h)        # Bottom Left Of The Quad (Front)
            glVertex3f( ratio2w,-ratio1h, ratio2h)        # Bottom Right Of The Quad (Front)
    
            glVertex3f( ratio2w,-ratio1h,-ratio2h)        # Bottom Left Of The Quad (Back)
            glVertex3f(-ratio2w,-ratio1h,-ratio2h)        # Bottom Right Of The Quad (Back)
            glVertex3f(-ratio2w, ratio1h,-ratio2h)        # Top Right Of The Quad (Back)
            glVertex3f( ratio2w, ratio1h,-ratio2h)        # Top Left Of The Quad (Back)
    
            glVertex3f(-ratio2w, ratio1h, ratio2h)        # Top Right Of The Quad (Left)
            glVertex3f(-ratio2w, ratio1h,-ratio2h)        # Top Left Of The Quad (Left)
            glVertex3f(-ratio2w,-ratio1h,-ratio2h)        # Bottom Left Of The Quad (Left)
            glVertex3f(-ratio2w,-ratio1h, ratio2h)        # Bottom Right Of The Quad (Left)
    
            glVertex3f( ratio2w, ratio1h,-ratio2h)        # Top Right Of The Quad (Right)
            glVertex3f( ratio2w, ratio1h, ratio2h)        # Top Left Of The Quad (Right)
            glVertex3f( ratio2w,-ratio1h, ratio2h)        # Bottom Left Of The Quad (Right)
            glVertex3f( ratio2w,-ratio1h,-ratio2h)        # Bottom Right Of The Quad (Right)
            glEnd()                # Done Drawing The Quad
    
    
            curCenter = -(( 1.0 * self.volumeEditor.selSlices[2] / self.sceneShape[2] ) - 0.5 )*2.0*ratio1h
            if axis is 2:
                if self.tex[2] != -1:
                    self.deleteTexture(self.tex[2])
                self.tex[2] = self.bindTexture(self.images[2].scene.image, GL_TEXTURE_2D, GL_RGB)
            if self.tex[2] != -1:
                glBindTexture(GL_TEXTURE_2D,self.tex[2])
                
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
                glPolygonMode( GL_FRONT_AND_BACK, GL_FILL ) #solid drawing mode

                glBegin(GL_QUADS) #horizontal quad (e.g. first axis)
                glColor3f(1.0,1.0,1.0)            # Set The Color To White
                glTexCoord2d(0.0, 1.0)
                glVertex3f( -ratio2w,curCenter, -ratio2h)        # Top Right Of The Quad
                glTexCoord2d(1.0, 1.0)
                glVertex3f(+ ratio2w,curCenter, -ratio2h)        # Top Left Of The Quad
                glTexCoord2d(1.0, 0.0)
                glVertex3f(+ ratio2w,curCenter, + ratio2h)        # Bottom Left Of The Quad
                glTexCoord2d(0.0, 0.0)
                glVertex3f( -ratio2w,curCenter, + ratio2h)        # Bottom Right Of The Quad
                glEnd()


                glPolygonMode( GL_FRONT_AND_BACK, GL_LINE ) #wireframe mode
                glBindTexture(GL_TEXTURE_2D,0) #unbind texture

                glBegin(GL_QUADS)
                glColor3f(0.0,0.0,1.0)            # Set The Color To Blue, Z Axis
                glVertex3f( ratio2w,curCenter, ratio2h)        # Top Right Of The Quad (Bottom)
                glVertex3f(- ratio2w,curCenter, ratio2h)        # Top Left Of The Quad (Bottom)
                glVertex3f(- ratio2w,curCenter,- ratio2h)        # Bottom Left Of The Quad (Bottom)
                glVertex3f( ratio2w,curCenter,- ratio2h)        # Bottom Right Of The Quad (Bottom)
                glEnd()
    
    
    
    
    
    
    
            curCenter = (( (1.0 * self.volumeEditor.selSlices[0]) / self.sceneShape[0] ) - 0.5 )*2.0*ratio2w
    
            if axis is 0:
                if self.tex[0] != -1:
                    self.deleteTexture(self.tex[0])
                self.tex[0] = self.bindTexture(self.images[0].scene.image, GL_TEXTURE_2D, GL_RGB)
            if self.tex[0] != -1:
                glBindTexture(GL_TEXTURE_2D,self.tex[0])


                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
                glPolygonMode( GL_FRONT_AND_BACK, GL_FILL ) #solid drawing mode

                glBegin(GL_QUADS)
                glColor3f(0.8,0.8,0.8)            # Set The Color To White
                glTexCoord2d(1.0, 1.0)
                glVertex3f(curCenter, ratio0h, ratio0w)        # Top Right Of The Quad (Left)
                glTexCoord2d(0.0, 1.0)
                glVertex3f(curCenter, ratio0h, - ratio0w)        # Top Left Of The Quad (Left)
                glTexCoord2d(0.0, 0.0)
                glVertex3f(curCenter,- ratio0h,- ratio0w)        # Bottom Left Of The Quad (Left)
                glTexCoord2d(1.0, 0.0)
                glVertex3f(curCenter,- ratio0h, ratio0w)        # Bottom Right Of The Quad (Left)
                glEnd()

                glPolygonMode( GL_FRONT_AND_BACK, GL_LINE ) #wireframe mode
                glBindTexture(GL_TEXTURE_2D,0) #unbind texture

                glBegin(GL_QUADS)
                glColor3f(1.0,0.0,0.0)            # Set The Color To Red,
                glVertex3f(curCenter, ratio0h, ratio0w)        # Top Right Of The Quad (Left)
                glVertex3f(curCenter, ratio0h, - ratio0w)        # Top Left Of The Quad (Left)
                glVertex3f(curCenter,- ratio0h,- ratio0w)        # Bottom Left Of The Quad (Left)
                glVertex3f(curCenter,- ratio0h, ratio0w)        # Bottom Right Of The Quad (Left)
                glEnd()
    
    
            curCenter = (( 1.0 * self.volumeEditor.selSlices[1] / self.sceneShape[1] ) - 0.5 )*2.0*ratio2h
    
    
            if axis is 1:
                if self.tex[1] != -1:
                    self.deleteTexture(self.tex[1])
                self.tex[1] = self.bindTexture(self.images[1].scene.image, GL_TEXTURE_2D, GL_RGB)
            if self.tex[1] != -1:
                glBindTexture(GL_TEXTURE_2D,self.tex[1])
    
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
                glPolygonMode( GL_FRONT_AND_BACK, GL_FILL ) #solid drawing mode

                glBegin(GL_QUADS)
                glColor3f(0.6,0.6,0.6)            # Set The Color To White
                glTexCoord2d(1.0, 1.0)
                glVertex3f( ratio1w,  ratio1h, curCenter)        # Top Right Of The Quad (Front)
                glTexCoord2d(0.0, 1.0)
                glVertex3f(- ratio1w, ratio1h, curCenter)        # Top Left Of The Quad (Front)
                glTexCoord2d(0.0, 0.0)
                glVertex3f(- ratio1w,- ratio1h, curCenter)        # Bottom Left Of The Quad (Front)
                glTexCoord2d(1.0, 0.0)
                glVertex3f( ratio1w,- ratio1h, curCenter)        # Bottom Right Of The Quad (Front)
                glEnd()

                glPolygonMode( GL_FRONT_AND_BACK, GL_LINE ) #wireframe mode
                glBindTexture(GL_TEXTURE_2D,0) #unbind texture
                glBegin(GL_QUADS)
                glColor3f(0.0,1.0,0.0)            # Set The Color To Green
                glVertex3f( ratio1w,  ratio1h, curCenter)        # Top Right Of The Quad (Front)
                glVertex3f(- ratio1w, ratio1h, curCenter)        # Top Left Of The Quad (Front)
                glVertex3f(- ratio1w,- ratio1h, curCenter)        # Bottom Left Of The Quad (Front)
                glVertex3f( ratio1w,- ratio1h, curCenter)        # Bottom Right Of The Quad (Front)
                glEnd()
    
            glFlush()

    def resizeGL(self, w, h):
        '''
        Resize the GL window
        '''

        glViewport(0, 0, w, h)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(40.0, 1.0, 1.0, 30.0)

    def initializeGL(self):
        '''
        Initialize GL
        '''

        # set viewing projection
        glClearColor(0.0, 0.0, 0.0, 1.0)
        glClearDepth(1.0)

        glDepthFunc(GL_LESS)                # The Type Of Depth Test To Do
        glEnable(GL_DEPTH_TEST)                # Enables Depth Testing
        glShadeModel(GL_SMOOTH)                # Enables Smooth Color Shading
        glEnable(GL_TEXTURE_2D)
        glLineWidth( 2.0 );

        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(40.0, 1.0, 1.0, 30.0)
        
        self.initialized = True

#class OverviewScene2(QtGui.QGraphicsView):
#    def __init__(self, images):
#        QtGui.QGraphicsView.__init__(self)
#        self.scene = QtGui.QGraphicsScene(self)
##        self.scene.setSceneRect(0,0, imShape[0],imShape[1])
#        self.setScene(self.scene)
#        self.setRenderHint(QtGui.QPainter.Antialiasing)
#        self.images = images
#        self.sceneItems = []
#
#    def display(self):
#        for index, item in enumerate(self.sceneItems):
#            self.scene.removeItem(item)
#            del item
#        self.sceneItems = []
#        self.sceneItems.append(QtGui.QGraphicsPixmapItem(self.images[0].pixmap))
#        self.sceneItems.append(QtGui.QGraphicsPixmapItem(self.images[1].pixmap))
#        self.sceneItems.append(QtGui.QGraphicsPixmapItem(self.images[2].pixmap))
#        for index, item in enumerate(self.sceneItems):
#            self.scene.addItem(item)

def test():
    """Text editor demo"""
    import numpy
    app = QtGui.QApplication([""])

    im = (numpy.random.rand(1024,1024)*255).astype(numpy.uint8)
    im[0:10,0:10] = 255
    
    dialog = VolumeEditor(im)
    dialog.show()
    app.exec_()
    del app

    app = QtGui.QApplication([""])

    im = (numpy.random.rand(128,128,128)*255).astype(numpy.uint8)
    im[0:10,0:10,0:10] = 255

    dialog = VolumeEditor(im)
    dialog.show()
    app.exec_()


if __name__ == "__main__":
    test()