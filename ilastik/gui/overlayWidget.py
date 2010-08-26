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

from PyQt4 import QtCore, QtGui
import vigra, numpy
import sip
import os
from overlaySelectionDlg import OverlaySelectionDialog


from ilastik.core.volume import DataAccessor, Volume, VolumeLabels, VolumeLabelDescription
from ilastik.core.overlayMgr import OverlayMgr,  OverlayItem, OverlaySlice


from enthought.mayavi import mlab
from ilastik.core.volume import DataAccessor, Volume, VolumeLabels, VolumeLabelDescription
from enthought.traits.api import HasTraits, Range, Instance, on_trait_change


from enthought.traits.ui.api import View, Item, Group

from enthought.mayavi.core.api import PipelineBase
from enthought.mayavi.core.ui.api import MayaviScene, SceneEditor, MlabSceneModel

################################################################################
#The actual visualization
class Maya3DScene(HasTraits):

    scene = Instance(MlabSceneModel, ())

    plot = Instance(PipelineBase)


    def __init__(self, item, raw):
        HasTraits.__init__(self)
        self.item = item
        self.raw = raw
        print self.item.shape, self.item.dtype
        

    # When the scene is activated, or when the parameters are changed, we
    # update the plot.
    @on_trait_change('scene.activated')
    def update_plot(self):
        if self.plot is None:
            self.dataField = self.scene.mlab.pipeline.scalar_field(self.item)
            self.rawField = self.scene.mlab.pipeline.scalar_field(self.raw)


#            self.xp = self.scene.mlab.pipeline.image_plane_widget(self.rawField,
#                            plane_orientation='x_axes',
#                            slice_index=10
#                            )
#            def move_slicex(obj, evt):
#                #print obj
#                print obj.GetCurrentCursorPosition()
#                print self.xp.ipw.slice_position
#
#            self.xp.ipw.add_observer('EndInteractionEvent', move_slicex)
#
#            self.yp = self.scene.mlab.pipeline.image_plane_widget(self.rawField,
#                            plane_orientation='y_axes',
#                            slice_index=10
#                        )
#            def move_slicey(obj, evt):
#                #print obj
#                print obj.GetCurrentCursorPosition()
#                print self.yp.ipw.slice_position
#
#            self.yp.ipw.add_observer('EndInteractionEvent', move_slicey)
#
#            self.zp = self.scene.mlab.pipeline.image_plane_widget(self.rawField,
#                            plane_orientation='z_axes',
#                            slice_index=10
#                        )
#            def move_slicez(obj, evt):
#                #print obj
#                print obj.GetCurrentCursorPosition()
#                print self.zp.ipw.slice_position
#
#            self.zp.ipw.add_observer('EndInteractionEvent', move_slicez)

            self.plot = self.scene.mlab.pipeline.iso_surface(self.dataField, opacity=0.4, contours=[2, 3, 4, 5, 6, 7])
            
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
        #mlab.close()



class OverlayListWidgetItem(QtGui.QListWidgetItem):
    def __init__(self, overlayItem):
        QtGui.QListWidgetItem.__init__(self,overlayItem.name)
        self.overlayItem = overlayItem
        self.name = overlayItem.name
        self.color = self.overlayItem.color
        self.visible = overlayItem.visible

        self.setFlags(self.flags() | QtCore.Qt.ItemIsUserCheckable)
        
        self.setCheckState(self.visible * 2)


class OverlayListWidget(QtGui.QListWidget):

    class QAlphaSliderDialog(QtGui.QDialog):
        def __init__(self, min, max, value):
            QtGui.QDialog.__init__(self)
            self.setWindowTitle('Change Alpha')
            self.slider = QtGui.QSlider(QtCore.Qt.Horizontal, self)
            self.slider.setGeometry(20, 30, 140, 20)
            self.slider.setRange(min,max)
            self.slider.setValue(value)

    def __init__(self,volumeEditor,  overlayWidget):
        QtGui.QListWidget.__init__(self, overlayWidget)
        self.volumeEditor = volumeEditor
        self.overlayWidget = overlayWidget
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.connect(self, QtCore.SIGNAL("customContextMenuRequested(QPoint)"), self.onContext)
        self.connect(self, QtCore.SIGNAL("clicked(QModelIndex)"), self.onItemClick)
        self.connect(self, QtCore.SIGNAL("doubleClicked(QModelIndex)"), self.onItemDoubleClick)
        self.currentItem = None
        #add the overlays to the gui
        for overlay in self.overlayWidget.overlays:
            if overlay.overlayItem != None:
                self.addItem(OverlayListWidgetItem(overlay))
            #dont forget to remove overlayreferences whose base overlayItem has been deleted from somewhere else by now:
            else:
                self.overlayWidget.overlays.remove(overlay)

    def onItemClick(self, itemIndex):
        item = self.itemFromIndex(itemIndex)
        if (item.checkState() == QtCore.Qt.Checked and not item.overlayItem.visible) or (item.checkState() == QtCore.Qt.Unchecked and item.overlayItem.visible):
            item.overlayItem.visible = not(item.overlayItem.visible)
            s = None
            if item.overlayItem.visible:
                s = QtCore.Qt.Checked
            else:
                s = QtCore.Qt.Unchecked
            item.setCheckState(s)
            self.volumeEditor.repaint()
            
    def onItemDoubleClick(self, itemIndex):
        self.currentItem = item = self.itemFromIndex(itemIndex)
        if item.checkState() == item.visible * 2:
            dialog = OverlayListWidget.QAlphaSliderDialog(1, 20, round(item.overlayItem.alpha*20))
            dialog.slider.connect(dialog.slider, QtCore.SIGNAL('valueChanged(int)'), self.setCurrentItemAlpha)
            dialog.exec_()
        else:
            self.onItemClick(itemIndex)
            
            
    def setCurrentItemAlpha(self, num):
        self.currentItem.overlayItem.alpha = 1.0 * num / 20.0
        self.volumeEditor.repaint()
        
#    def clearOverlays(self):
#        self.clear()
#        self.overlayWidget.overlays = []

    def removeOverlay(self, item):
        itemNr = None
        if isinstance(item, str):
            for idx, it in enumerate(self.overlayWidget.overlays):
                if it.name == item:
                    itemNr = idx
                    item = it
        else:
            itemNr = item
        if itemNr != None:
            self.overlayWidget.overlays.pop(itemNr)
            self.takeItem(itemNr)
            return item
        else:
            return None

    def addOverlayRef(self, overlayRef):
        self.addItem(OverlayListWidgetItem(overlayRef))

    def onContext(self, pos):
        index = self.indexAt(pos)

        if not index.isValid():
           return

        item = self.itemAt(pos)
        name = item.text()

        menu = QtGui.QMenu(self)

        show3dAction = menu.addAction("Display 3D")
        colorAction = menu.addAction("Change Color")

        channelMenu = QtGui.QMenu("Select Channel", menu)
        channelActions = []
        for i in range(item.overlayItem.numChannels):
            action = channelMenu.addAction(str(i))
            channelActions.append(action)

        action = menu.exec_(QtGui.QCursor.pos())
        if action == show3dAction:
#            mlab.contour3d(item.data[0,:,:,:,0], opacity=0.6)
#            mlab.outline()
            my_model = MayaviQWidget(item.overlayItem.data[0,:,:,:,0], self.volumeEditor.image[0,:,:,:,0])
            my_model.show()
        elif action == colorAction:
            color = QtGui.QColorDialog().getColor()
            item.overlayItem.colorTable = None
            item.overlayItem.color = color
            self.volumeEditor.repaint()
        else:
            for index,  channelAct in enumerate(channelActions):
                if action == channelAct:
                    item.overlayItem.setChannel(index)




    def getLabelNames(self):
        labelNames = []
        for idx, it in enumerate(self.descriptions):
            labelNames.append(it.name)
        return labelNames
       
      
    def toggleVisible(self,  index):
        state = not(item.overlayItem.visible)
        item.overlayItem.visible = state
        item.setCheckState(item.overlayItem.visible * 2)
        
        
    def wheelEvent(self, event):
        pos = event.pos()
        item = self.itemAt(pos)
        
        if event.delta() > 0:
            item.overlayItem.incChannel()
        else:
            item.overlayItem.decChannel()
        self.volumeEditor.repaint()
        


class OverlayWidget(QtGui.QGroupBox):
    def __init__(self,parent, overlayMgr,  overlays):
        QtGui.QGroupBox.__init__(self,  "Overlays")
        self.setLayout(QtGui.QHBoxLayout())
        
        self.overlayMgr = overlayMgr
        
        self.overlays = overlays

        self.overlayListWidget = OverlayListWidget(parent, self)
       
        tl1 = QtGui.QVBoxLayout()
        tl1.addWidget(self.overlayListWidget)

        pathext = os.path.dirname(__file__)

        tl2 = QtGui.QHBoxLayout()
        self.buttonAdd = QtGui.QPushButton()
        self.buttonAdd.setIcon(QtGui.QIcon(pathext + "/icons/22x22/actions/list-add.png") )
        self.connect(self.buttonAdd,  QtCore.SIGNAL('clicked()'),  self.buttonAddClicked)
        self.buttonRemove = QtGui.QPushButton()
        self.buttonRemove.setIcon(QtGui.QIcon(pathext + "/icons/22x22/actions/list-remove.png"))
        self.connect(self.buttonRemove,  QtCore.SIGNAL('clicked()'),  self.buttonRemoveClicked)
        tl2.addWidget(self.buttonAdd)
        tl2.addWidget(self.buttonRemove)
        tl1.addLayout(tl2)
        
        
        tl3 = QtGui.QVBoxLayout()
        tl3.addStretch()
        self.buttonUp = QtGui.QPushButton()
        self.buttonUp.resize(10, 10)
        self.buttonUp.setSizePolicy(QtGui.QSizePolicy.Fixed,  QtGui.QSizePolicy.Fixed)
        self.buttonDown = QtGui.QPushButton()
        self.buttonDown.resize(10, 10)
        self.buttonDown.setSizePolicy(QtGui.QSizePolicy.Fixed,  QtGui.QSizePolicy.Fixed)
        tl3.addWidget(self.buttonUp)
        tl3.addWidget(self.buttonDown)
        tl3.addStretch()
        
        self.layout().addLayout(tl1)
        #self.layout().addLayout(tl3)
        
    def buttonAddClicked(self):
        dlg = OverlaySelectionDialog(self.overlayMgr,  singleSelection = False)
        answer = dlg.exec_()
        for o in answer:
            self.addOverlayRef(o.getRef())
        self.overlayListWidget.volumeEditor.repaint()
        
    def buttonRemoveClicked(self):
        number = self.overlayListWidget.currentRow()
        if number >= 0:
            self.overlayListWidget.removeOverlay(number)
            self.overlayListWidget.volumeEditor.repaint()
        
    def removeOverlay(self, item):
        """
        item can be a string, e.g. the item name, or a number
        """
        return self.overlayListWidget.removeOverlay(item)
        
    def addOverlayRef(self, overlayRef):
        self.overlays.append(overlayRef)
        return self.overlayListWidget.addOverlayRef(overlayRef)

    def getLabelNames(self):
        return self.overlayListWidget.getLabelNames()
       
    def toggleVisible(self,  index):
        return self.overlayListWidget.toggleVisible(index)

    def getOverlayRef(self,  key):
        """
        find a specific overlay via its key e.g. "Classification/Prediction" in the
        current overlays of the widget
        """
        for o in self.overlays:
            if o.key == key:
                return o
        return None
