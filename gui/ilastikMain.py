#!/usr/bin/env python
# profile with python -m cProfile ilastikMain.py
# python -m cProfile -o profiling.prf  ilastikMain.py
# import pstats
# p = pstats.Stats('fooprof')
# p.sort_statsf('time').reverse_order().print_stats()
# possible sort order: "stdname" "calls" "time" "cumulative". more in p.sort_arg_dic
import vigra
from vigra import arraytypes as at

import sys
import os

import threading 
import numpy
import time
from PyQt4 import QtCore, QtGui, uic
from core import version, dataMgr, projectMgr, featureMgr, classificationMgr, segmentationMgr, activeLearning, onlineClassifcator
from gui import ctrlRibbon, imgLabel
from Queue import Queue as queue
from collections import deque
from gui.iconMgr import ilastikIcons
from core.utilities import irange, debug

class MainWindow(QtGui.QMainWindow):
    def __init__(self, parent=None):
        QtGui.QMainWindow.__init__(self)
        self.setGeometry(50, 50, 800, 600)
        self.iconPath = '../../icons/32x32/'
        self.setWindowTitle("Ilastik rev: " + version.getIlastikVersion())
        self.setWindowIcon(QtGui.QIcon(ilastikIcons.Python))
        
        self.createRibbons()
        self.initImageWindows()
        self.createImageWindows()
        self.createFeatures()
        
        #self.labelDocks=[]
        #self.labelWidget = None
        
        self.classificationProcess = None
        self.classificationOnline = None
                
    def createRibbons(self):                     
      
        self.ribbonToolbar = self.addToolBar("ToolBarForRibbons")
        
        self.ribbon = ctrlRibbon.Ribbon(self.ribbonToolbar)
        for ribbon_name, ribbon_group in ctrlRibbon.createRibbons().items():
            tabs = ribbon_group.makeTab()   
            self.ribbon.addTab(tabs, ribbon_group.name)  
        self.ribbonToolbar.addWidget(self.ribbon)
        
        # Wee, this is really ugly... anybody have better ideas for connecting 
        # the signals. This way has no future and is just a worka    round
        
        self.connect(self.ribbon.tabDict['Projects'].itemDict['New'], QtCore.SIGNAL('clicked()'), self.newProjectDlg)
        self.connect(self.ribbon.tabDict['Projects'].itemDict['Save'], QtCore.SIGNAL('clicked()'), self.saveProjectDlg)
        self.connect(self.ribbon.tabDict['Projects'].itemDict['Open'], QtCore.SIGNAL('clicked()'), self.loadProjectDlg)
        self.connect(self.ribbon.tabDict['Projects'].itemDict['Edit'], QtCore.SIGNAL('clicked()'), self.editProjectDlg)
        self.connect(self.ribbon.tabDict['Features'].itemDict['Select'], QtCore.SIGNAL('clicked()'), self.newFeatureDlg)
        self.connect(self.ribbon.tabDict['Features'].itemDict['Compute'], QtCore.SIGNAL('clicked()'), self.featureCompute)
        self.connect(self.ribbon.tabDict['Classification'].itemDict['Train'], QtCore.SIGNAL('clicked()'), self.on_classificationTrain)
        self.connect(self.ribbon.tabDict['Classification'].itemDict['Predict'], QtCore.SIGNAL('clicked()'), self.on_classificationPredict)
        self.connect(self.ribbon.tabDict['Classification'].itemDict['Interactive'], QtCore.SIGNAL('clicked(bool)'), self.on_classificationInteractive)
        self.connect(self.ribbon.tabDict['Classification'].itemDict['Online'], QtCore.SIGNAL('clicked(bool)'), self.on_classificationOnline)
        self.connect(self.ribbon.tabDict['Segmentation'].itemDict['Segment'], QtCore.SIGNAL('clicked(bool)'), self.on_segmentation)
        self.connect(self.ribbon.tabDict['Label'].itemDict['Brushsize'], QtCore.SIGNAL('valueChanged(int)'), self.on_changeBrushSize)
        
        # Make menu for online Classification
        btnOnlineToggle = self.ribbon.tabDict['Classification'].itemDict['Online']
        btnOnlineToggle.myMenu = QtGui.QMenu();
        btnOnlineToggle.onlineRfAction = btnOnlineToggle.myMenu.addAction('Online RF')
        btnOnlineToggle.onlineSVMAction = btnOnlineToggle.myMenu.addAction('Online SVM')
        btnOnlineToggle.onlineStopAction = btnOnlineToggle.myMenu.addAction('Stop')
        btnOnlineToggle.onlineStopAction.setEnabled(False)
        btnOnlineToggle.setMenu(btnOnlineToggle.myMenu)
        btnOnlineToggle.setPopupMode(2)
        
        self.connect(btnOnlineToggle.onlineRfAction, QtCore.SIGNAL('triggered()'), lambda : self.on_classificationOnline('online RF'))
        self.connect(btnOnlineToggle.onlineSVMAction, QtCore.SIGNAL('triggered()'), lambda : self.on_classificationOnline('online laSvm'))
        self.connect(btnOnlineToggle.onlineStopAction, QtCore.SIGNAL('triggered()'), lambda : self.on_classificationOnline('stop'))
        
        # make LabelTab and View Tab invisible (this tabs are not helpful so far)
        self.ribbon.removeTab(1)
        self.ribbon.removeTab(1)
        
        #add classificator for online
        #self.ribbon.tabDict['Classification'].itemDict['OnlineClassificator'].addItem('online laSvm')
        #self.ribbon.tabDict['Classification'].itemDict['OnlineClassificator'].addItem('online RF')
        
        
        self.connect(self.ribbon.tabDict['Export'].itemDict['Export'], QtCore.SIGNAL('clicked()'), self.export2Hdf5)
        
        self.ribbon.tabDict['Projects'].itemDict['Edit'].setEnabled(False)
        self.ribbon.tabDict['Projects'].itemDict['Save'].setEnabled(False)
        
        
        #self.ribbon.tabDict['Features'].itemDict['Compute'].setEnabled(False)
        #self.ribbon.tabDict['Classification'].itemDict['Compute'].setEnabled(False)
        
        self.ribbon.setCurrentIndex (0)
          
    def newProjectDlg(self):      
        self.projectDlg = ProjectDlg(self)
    
    def saveProjectDlg(self):
        self.labelWidget.updateLabelsOfDataItems(self.project.dataMgr)
        fileName = QtGui.QFileDialog.getSaveFileName(self, "Save Project", ".", "Project Files (*.ilp)")
        self.project.saveToDisk(str(fileName))
        
    def loadProjectDlg(self):
        fileName = QtGui.QFileDialog.getOpenFileName(self, "Open Project", ".", "Project Files (*.ilp)")
        self.project = projectMgr.Project.loadFromDisk(str(fileName))
        self.ribbon.tabDict['Projects'].itemDict['Edit'].setEnabled(True)
        self.ribbon.tabDict['Projects'].itemDict['Save'].setEnabled(True)
        self.projectModified() 
        
    def editProjectDlg(self):
        if hasattr(self, 'projectDlg'):
            self.labelWidget.updateLabelsOfDataItems(self.project.dataMgr)
            self.projectDlg.show()
            return
        else:        
            self.projectDlg = ProjectDlg(self)
            self.projectDlg.updateDlg(self.project)
            self.projectModified()
            
        
    def projectModified(self):
        self.destroyImageWindows()
        self.createImageWindows()
        self.labelWidget.updateProject(self.project)
        
    def newFeatureDlg(self):
        self.newFeatureDlg = FeatureDlg(self)
        
    def newEditChannelsDlg(self):
        self.editChannelsDlg = editChannelsDlg(self)
        
    def initImageWindows(self):
        self.labelDocks = []
        
    def destroyImageWindows(self):
        for dock in self.labelDocks:
            self.removeDockWidget(dock)
        self.labelDocks = []
        self.labelWidget = None
                
    def createImageWindows(self):
        label_w = imgLabel.labelWidget(self, ['rgb1.jpg', 'rgb2.tif'])
        
        dock = QtGui.QDockWidget("Ilastik Label Widget", self)
        dock.setAllowedAreas(QtCore.Qt.BottomDockWidgetArea | QtCore.Qt.RightDockWidgetArea | QtCore.Qt.TopDockWidgetArea | QtCore.Qt.LeftDockWidgetArea)
        dock.setWidget(label_w)
        self.labelWidget = label_w  # todo: user defined list of labelwidgets
        
        area = QtCore.Qt.BottomDockWidgetArea
        
        self.addDockWidget(area, dock)
        self.labelDocks.append(dock)
    def createFeatures(self):
        self.featureList = featureMgr.ilastikFeatures
        
    def featureCompute(self):
        self.featureComputation = FeatureComputation(self)
    
    def on_segmentation(self):

        segThreads = []
        seg = []
        for shape, propmap in zip(self.project.dataMgr.dataItemsShapes(), self.project.dataMgr.prediction):
            s = segmentationMgr.LocallyDominantSegmentation2D(shape)
            seg.append(s)
            
            t = threading.Thread(target=s.segment, args=(propmap,))
            segThreads.append(t)
            t.start()         
        
        for cnt, t in irange(segThreads):
            t.join()
            self.project.dataMgr.segmentation[cnt] = seg[cnt].result
        
        self.labelWidget.OverlayMgr.updateSegmentationPixmaps(dict(irange(self.project.dataMgr.segmentation)))
        self.labelWidget.OverlayMgr.setOverlayState('Segmentation')
        
    def on_changeBrushSize(self, rad):
        #if rad / 2 != 0:
        #    rad + 1 
            
        self.labelWidget.setBrushSize(rad)

    def on_classificationTrain(self):
        self.classificationTrain = ClassificationTrain(self)
        
    def on_classificationPredict(self):
        self.classificationPredict = ClassificationPredict(self)
    
    def on_classificationInteractive(self, state):
        if state:
            self.generateTrainingData()
            self.classificationInteractive = ClassificationInteractive(self)
        else:
            self.classificationInteractive.stop()
            
    def on_classificationOnline(self, state):
        btnOnlineToggle = self.ribbon.tabDict['Classification'].itemDict['Online']
        if state in ['online RF', 'online laSvm']:
            print "create and Start new Online"
            self.classificationOnline = ClassificationOnline(self)
            self.classificationOnline.start(state)
            btnOnlineToggle.onlineRfAction.setEnabled(False)
            btnOnlineToggle.onlineSVMAction.setEnabled(False)
            btnOnlineToggle.onlineStopAction.setEnabled(True)
        else:
            print "Stop Online"
            self.classificationOnline.stop()
            btnOnlineToggle.onlineRfAction.setEnabled(True)
            btnOnlineToggle.onlineSVMAction.setEnabled(True)
            btnOnlineToggle.onlineStopAction.setEnabled(False)
        
    # TODO: This whole function should NOT be here transfer it DataMgr. 
    def generateTrainingData(self,labelArrays=None):
        trainingMatrices_perDataItem = []
        res_labels = []
        res_names = []
        dataItemNr = 0
        for dataItem in self.project.dataMgr.dataFeatures:
            res_labeledFeatures = []

            if not self.labelWidget.labelForImage.get(dataItemNr, None):
                # No Labels available for that image
                continue
            
            # Extract labelMatrix
            if labelArrays==None:
                labelmatrix = self.labelWidget.labelForImage[dataItemNr].DrawManagers[0].labelmngr.labelArray
            else:
                labelmatrix = labelArrays[dataItemNr]
            labeled_indices = labelmatrix.nonzero()[0]
            n_labels = labeled_indices.shape[0]
            nFeatures = 0
            for featureImage, featureString, c_ind in dataItem:
                # todo: fix hardcoded 2D:
                n = 1   # n: number of feature-values per pixel
                if featureImage.shape.__len__() > 2:
                    n = featureImage.shape[2]
                if n <= 1:
                    res_labeledFeatures.append(featureImage.flat[labeled_indices].reshape(1, n_labels))
                    if dataItemNr == 0:
                        res_names.append(featureString)
                else:
                    for featureDim in xrange(n):
                        res_labeledFeatures.append(featureImage[:, :, featureDim].flat[labeled_indices].reshape(1, n_labels))
                        if dataItemNr == 0:
                            res_names.append(featureString + "_%i" % (featureDim))
                nFeatures += 1
            if (dataItemNr == 0):
                nFeatures_ofFirstImage = nFeatures
            if nFeatures == nFeatures_ofFirstImage:
                trainingMatrices_perDataItem.append(numpy.concatenate(res_labeledFeatures).T)
                res_labels.append(labelmatrix[labeled_indices])
            else:
                print "feature dimensions don't match (maybe #channels differ?). Skipping image."
            dataItemNr += 1
        trainingMatrix = numpy.concatenate(trainingMatrices_perDataItem)
        self.project.trainingMatrix = trainingMatrix
        self.project.trainingLabels = numpy.concatenate(res_labels)
        self.project.trainingFeatureNames = res_names
        
        debug(trainingMatrix.shape)
        debug(self.project.trainingLabels.shape)
    
    def export2Hdf5(self):
        fileName = QtGui.QFileDialog.getSaveFileName(self, "Export Features, Labels and Prediction", ".", "HDF5 FIles (*.h5)")
        self.labelWidget.updateLabelsOfDataItems(self.project.dataMgr)
        self.project.dataMgr.export2Hdf5(str(fileName))
        
class ProjectDlg(QtGui.QDialog):
    def __init__(self, parent=None):
        QtGui.QWidget.__init__(self)
        # this enables   self.columnPos['File']:
        self.labelCounter = 2
        self.columnPos = {}
        self.labelColor = { 1:QtGui.QColor(QtCore.Qt.red), 2:QtGui.QColor(QtCore.Qt.green), 3:QtGui.QColor(QtCore.Qt.yellow), 4:QtGui.QColor(QtCore.Qt.blue), 5:QtGui.QColor(QtCore.Qt.magenta) , 6:QtGui.QColor(QtCore.Qt.darkYellow), 7:QtGui.QColor(QtCore.Qt.lightGray) }
        self.parent = parent
        self.fileList = []
        self.thumbList = []        
        self.initDlg()
        self.on_cmbLabelName_currentIndexChanged(0)
        self.setLabelColorButtonColor(QtGui.QColor(QtCore.Qt.red))
        for i in xrange(self.tableWidget.columnCount()):
            self.columnPos[ str(self.tableWidget.horizontalHeaderItem(i).text()) ] = i
        self.defaultLabelColors = {}
        
    def initDlg(self):
        uic.loadUi('gui/dlgProject.ui', self) 
        self.tableWidget.resizeRowsToContents()
        self.tableWidget.resizeColumnsToContents()
        self.tableWidget.setAlternatingRowColors(True)
        self.tableWidget.setShowGrid(False)
        self.tableWidget.horizontalHeader().setResizeMode(0, QtGui.QHeaderView.Stretch)
        self.tableWidget.verticalHeader().hide()
        self.connect(self.tableWidget, QtCore.SIGNAL("cellPressed(int, int)"), self.updateThumbnail)
        #self.on_cmbLabelName_currentIndexChanged(0)
        self.show()
        

    @QtCore.pyqtSignature("int")
    def on_cmbLabelName_currentIndexChanged(self, nr):
        if nr < 0:
            return
        nr += 1 # 0 is unlabeled !!
        self.txtLabelName.setText(self.cmbLabelName.currentText())
        #col = QtGui.QColor.fromRgb(self.labelColor.get(nr, QtGui.QColor(QtCore.Qt.red).rgb()))
        if not self.labelColor.get(nr, None):
            if nr > len(self.labelColor):
                self.labelColor[nr] = QtGui.QColor(numpy.random.randint(255), numpy.random.randint(255), numpy.random.randint(255))  # default: red
        col = self.labelColor[nr]
        self.setLabelColorButtonColor(col)

    @QtCore.pyqtSignature("")
    def on_btnAddLabel_clicked(self):
        self.cmbLabelName.addItem("Class %d" % self.labelCounter)
        self.cmbLabelName.setCurrentIndex(self.cmbLabelName.count() - 1)
        self.labelCounter += 1
        #self.on_cmbLabelName_currentIndexChanged( self.cmbLabelName.count()-1 )
        
    def setLabelColorButtonColor(self, col):
        self.btnLabelColor.setAutoFillBackground(True)
        fgcol = QtGui.QColor()
        fgcol.setRed(255 - col.red())
        fgcol.setGreen(255 - col.green())
        fgcol.setBlue(255 - col.blue())
        self.btnLabelColor.setStyleSheet("background-color: %s; color: %s" % (col.name(), fgcol.name()))

    @QtCore.pyqtSignature("") 
    def on_btnLabelColor_clicked(self):
        colordlg = QtGui.QColorDialog()
        col = colordlg.getColor()
        labelnr = self.cmbLabelName.currentIndex() + 1
        self.labelColor[labelnr] = col
        self.setLabelColorButtonColor(col)
        
    @QtCore.pyqtSignature("QString")
    def on_txtLabelName_textChanged(self, text):
        self.cmbLabelName.setItemText(self.cmbLabelName.currentIndex(), text)

    @QtCore.pyqtSignature("")
    def updateDlg(self, project):
        self.projectName.setText(project.name)
        self.labeler.setText(project.labeler)
        self.description.setText(project.description)
        
        theFlag = QtCore.Qt.ItemIsEnabled
        flagON = ~theFlag | theFlag 
        flagOFF = ~theFlag
            
        for d in project.dataMgr.dataItems:
            rowCount = self.tableWidget.rowCount()
            self.tableWidget.insertRow(0)
            
            # File Name
            r = QtGui.QTableWidgetItem(d.fileName)
            self.tableWidget.setItem(0, self.columnPos['File'], r)
            
            r = QtGui.QComboBox()
            r.setEditable(True)
            self.tableWidget.setCellWidget(0, self.columnPos['Groups'], r)
            
            # Here comes the cool python "checker" use it for if_than_else in lambdas
            checker = lambda x: x and QtCore.Qt.Checked or QtCore.Qt.Unchecked
            
            # labels
            r = QtGui.QTableWidgetItem()
            r.data(QtCore.Qt.CheckStateRole)
            r.setCheckState(checker(d.hasLabels))
            r.setFlags(r.flags() & flagOFF);
            self.tableWidget.setItem(0, self.columnPos['Labels'], r)
            
            # train
            r = QtGui.QTableWidgetItem()
            r.data(QtCore.Qt.CheckStateRole)
            r.setCheckState(checker(d.isTraining))
            r.setFlags(r.flags() & flagON);
            self.tableWidget.setItem(0, self.columnPos['Train'], r)
            
            # test
            r = QtGui.QTableWidgetItem()
            r.data(QtCore.Qt.CheckStateRole)
            r.setCheckState(checker(d.isTesting))
            r.setFlags(r.flags() & flagON);
            self.tableWidget.setItem(0, self.columnPos['Test'], r)                  
        
        self.cmbLabelName.clear()
        self.labelColor = project.labelColors
        for name in project.labelNames:
            self.cmbLabelName.addItem(name)
        
        self.show()
        self.update()
        
    @QtCore.pyqtSignature("")     
    def on_addFile_clicked(self):
        
        fileNames = QtGui.QFileDialog.getOpenFileNames(self, "Open Image", ".", "Image Files (*.png *.jpg *.bmp *.tif *.gif);;Multi Spectral Data (*.h5)")
        if fileNames:
            for file_name in fileNames:
                self.fileList.append(file_name)
                rowCount = self.tableWidget.rowCount()
                self.tableWidget.insertRow(0)
                
                theFlag = QtCore.Qt.ItemIsEnabled
                flagON = ~theFlag | theFlag 
                flagOFF = ~theFlag
                
                # file name
                r = QtGui.QTableWidgetItem(file_name)
                self.tableWidget.setItem(0, self.columnPos['File'], r)
                
                # group
                r = QtGui.QComboBox()
                r.setEditable(True)
                self.tableWidget.setCellWidget(0, self.columnPos['Groups'], r)
                
                # labels
                r = QtGui.QTableWidgetItem()
                r.data(QtCore.Qt.CheckStateRole)
                r.setCheckState(QtCore.Qt.Unchecked)
                
                labelsAvailable = dataMgr.DataImpex.checkForLabels(file_name)
                if labelsAvailable:
                    r.setFlags(r.flags() & flagON);
                    print "Found %d labels" % labelsAvailable
                    for k in range(labelsAvailable-1):
                        if self.labelCounter <= labelsAvailable:
                            self.on_btnAddLabel_clicked()
                else:
                    r.setFlags(r.flags() & flagOFF);
                self.tableWidget.setItem(0, self.columnPos['Labels'], r)
                
                # train
                r = QtGui.QTableWidgetItem()
                r.data(QtCore.Qt.CheckStateRole)
                r.setCheckState(QtCore.Qt.Checked)
                r.setFlags(r.flags() & flagON);
                self.tableWidget.setItem(0, self.columnPos['Train'], r)
                
                # test
                r = QtGui.QTableWidgetItem()
                r.data(QtCore.Qt.CheckStateRole)
                r.setCheckState(QtCore.Qt.Checked)
                r.setFlags(r.flags() & flagON);
                self.tableWidget.setItem(0, self.columnPos['Test'], r)
                
                self.initThumbnail(file_name)
                self.tableWidget.setCurrentCell(0, 0)
    
    def on_removeFile_clicked(self):
        row = self.tableWidget.currentRow()
        
        
    def initThumbnail(self, file_name):
        thumb = QtGui.QPixmap(str(file_name))
        thumb = thumb.scaledToWidth(128)
        self.thumbList.append(thumb)
        self.thumbnailImage.setPixmap(self.thumbList[-1])
                    
    def updateThumbnail(self, row=0, col=0):
        self.thumbnailImage.setPixmap(self.thumbList[-row - 1]) 
    
    @QtCore.pyqtSignature("")     
    def on_confirmButtons_accepted(self):
        projectName = self.projectName
        labeler = self.labeler
        description = self.description
        
        # New project or edited project? if edited, reuse parts of old dataMgr
        if hasattr(self.parent,'project'):
            dm = self.parent.project.dataMgr
        else:
            dm = dataMgr.DataMgr()
        
        self.parent.project = projectMgr.Project(str(projectName.text()), str(labeler.text()), str(description.toPlainText()) , dm)
        
        # Set Class Count
        self.parent.project.classCount = self.cmbLabelName.count()
        
        # Set class Colors
        self.parent.project.labelColors = self.labelColor
        
        # Delete not used labelColors
        for i in xrange(1, len(self.labelColor)+1):
            if i > self.parent.project.classCount:
                del self.parent.project.labelColors[i]
                
        # Set label names
        self.parent.project.labelNames = []
        for i in xrange(self.parent.project.classCount):
            self.parent.project.labelNames.append(str(self.cmbLabelName.itemText(i)))
            
        rowCount = self.tableWidget.rowCount()
        dataItemList = self.parent.project.dataMgr.getDataList()
        oldDataFileNames = [str(k.fileName) for k in self.parent.project.dataMgr]
        for k in range(0, rowCount):
                 
            fileName = str(self.tableWidget.item(k, self.columnPos['File']).text())
            if fileName in oldDataFileNames:
                # Old File
                continue
            
            theDataItem = dataMgr.DataItemImage(fileName)
            self.parent.project.dataMgr.append(theDataItem)
            
            groups = []
            for i in xrange(self.tableWidget.cellWidget(k, self.columnPos['Groups']).count()):
                groups.append(str(self.tableWidget.cellWidget(k, self.columnPos['Groups']).itemText(i)))
            theDataItem.groupMembership = groups
            
            theDataItem.hasLabels = self.tableWidget.item(k, self.columnPos['Labels']).checkState() == QtCore.Qt.Checked
            theDataItem.isTraining = self.tableWidget.item(k, self.columnPos['Train']).checkState() == QtCore.Qt.Checked
            theDataItem.isTesting = self.tableWidget.item(k, self.columnPos['Test']).checkState() == QtCore.Qt.Checked
            
            
            
            contained = False
            for pr in theDataItem.projects:
                if pr == self.parent.project:
                    contained = true
            if not contained:
                theDataItem.projects.append(self.parent.project)
        
        dataItemList.sort(lambda x, y: cmp(x.fileName, y.fileName))    
        #self.parent.project.dataMgr.setDataList(dataItemList)
        self.parent.ribbon.tabDict['Projects'].itemDict['Edit'].setEnabled(True)
        self.parent.ribbon.tabDict['Projects'].itemDict['Save'].setEnabled(True)
        
        self.parent.projectModified()
        self.close()
        
    
    @QtCore.pyqtSignature("")    
    def on_confirmButtons_rejected(self):
        self.close()

class editChannelsDlg(QtGui.QDialog):
    def __init__(self, parent=None):
        QtGui.QWidget.__init__(self)
        self.parent = parent
        uic.loadUi('gui/dlgChannels.ui', self)
        self.show()
        
        dataMgr = parent.project.dataMgr
        
        channelNames = dataMgr[0].channelDescription
        channelUsed = dataMgr[0].channelUsed
        self.channelTab.horizontalHeader().resizeSection(1, 54)
        self.channelTab.horizontalHeader().setResizeMode(0, QtGui.QHeaderView.Stretch)
        
        checker = lambda x: x and QtCore.Qt.Checked or QtCore.Qt.Unchecked
        for k, cName in irange(channelNames): 
            itName = QtGui.QTableWidgetItem(channelNames[k])
            self.channelTab.insertRow(k)
            self.channelTab.setItem(k,0,itName)
            
            itUsed = QtGui.QTableWidgetItem()
            itUsed.data(QtCore.Qt.CheckStateRole)
            itUsed.setCheckState(checker(channelUsed[k]))
            self.channelTab.setItem(k,1,itUsed)
            #self.channelTab.verticalHeader().resizeRowToContents(k)
    
    def on_confirmButtons_rejected(self):
        self.close()
        
    def on_confirmButtons_accepted(self):
        dataMgr = self.parent.project.dataMgr
        newChannelNames = []
        newChannelUsed = []
        # get edits
        for k in xrange(self.channelTab.rowCount()):
            self.close()
            itName = str(self.channelTab.item(k,0).text())
            itUsed = self.channelTab.item(k,1).checkState()
            
            newChannelNames.append(itName)
            newChannelUsed.append(bool(int(itUsed)))
        
        # write them into dataMgr
        for dataItem in dataMgr:
            dataItem.channelDescription = newChannelNames
            dataItem.channelUsed = newChannelUsed
            
        # update checkbox
        self.parent.labelWidget.loadChannelList()
        self.close()
            
            
        
        
        

class FeatureDlg(QtGui.QDialog):
    def __init__(self, parent=None):
        QtGui.QWidget.__init__(self)
        self.parent = parent
        self.initDlg()
        
    def initDlg(self):
        uic.loadUi('gui/dlgFeature.ui', self) 
        for featureItem in self.parent.featureList:
            self.featureList.insertItem(self.featureList.count() + 1, QtCore.QString(featureItem.__str__()))        
        
        for k, groupName in irange(featureMgr.ilastikFeatureGroups.groupNames):
            rc = self.featureTable.rowCount()
            self.featureTable.insertRow(rc)
        self.featureTable.setVerticalHeaderLabels(featureMgr.ilastikFeatureGroups.groupNames)
        
        for k, scaleName in irange(featureMgr.ilastikFeatureGroups.groupScaleNames):
            rc = self.featureTable.columnCount()
            self.featureTable.insertColumn(rc)
        self.featureTable.setHorizontalHeaderLabels(featureMgr.ilastikFeatureGroups.groupScaleNames)
        
        self.featureTable.resizeRowsToContents()
        self.featureTable.resizeColumnsToContents()
        for c in range(self.featureTable.columnCount()):
            self.featureTable.horizontalHeader().resizeSection(c, 54)#(0, QtGui.QHeaderView.Stretch)

        self.featureTable.verticalHeader().setResizeMode(0, QtGui.QHeaderView.Stretch)
        self.featureTable.setShowGrid(False)
        
        
        for r in range(self.featureTable.rowCount()):
            for c in range(self.featureTable.columnCount()):
                item = QtGui.QTableWidgetItem()
                if featureMgr.ilastikFeatureGroups.selection[r][c]:
                    item.setIcon(QtGui.QIcon(ilastikIcons.Preferences))
                self.featureTable.setItem(r, c, item)
        self.setStyleSheet("selection-background-color: qlineargradient(x1: 0, y1: 0, x2: 0.5, y2: 0.5, stop: 0 #BBBBDD, stop: 1 white)")
        self.show()
    
    def on_featureTable_itemSelectionChanged(self):  
        sel = self.featureTable.selectedItems()
        sel_flag = False
        for i in sel:
            if i.icon().isNull():
                sel_flag = True
        
        if sel_flag:
            for i in sel:
                icon = QtGui.QIcon(ilastikIcons.Preferences)
                i.setIcon(icon)
                featureMgr.ilastikFeatureGroups.selection[i.row()][i.column()] = True  
                           
        else:
            for i in sel:
                icon = QtGui.QIcon()
                i.setIcon(icon)   
                featureMgr.ilastikFeatureGroups.selection[i.row()][i.column()] = False     
        
    @QtCore.pyqtSignature("")     
    def on_confirmButtons_accepted(self):  
        self.parent.project.featureMgr = featureMgr.FeatureMgr()

        featureSelectionList = []
        for k in range(0, self.featureList.count()):
            if self.featureList.item(k).isSelected():
                featureSelectionList.append(self.parent.featureList[k])
        
        featureSelectionList = featureMgr.ilastikFeatureGroups.createList()
        self.parent.project.featureMgr.setFeatureItems(featureSelectionList)
        self.close()
        #self.parent.projectModified()
        
    @QtCore.pyqtSignature("")    
    def on_confirmButtons_rejected(self):
        self.close()

class FeatureComputation(object):
    def __init__(self, parent):
        self.parent = parent
        self.featureCompute()
    
    def featureCompute(self):
        self.myTimer = QtCore.QTimer()
        self.parent.connect(self.myTimer, QtCore.SIGNAL("timeout()"), self.updateFeatureProgress)
        
        numberOfJobs = self.parent.project.featureMgr.prepareCompute(self.parent.project.dataMgr)  
        self.initFeatureProgress(numberOfJobs)
        self.parent.project.featureMgr.triggerCompute()
        self.myTimer.start(200) 
        
    def initFeatureProgress(self, numberOfJobs):
        statusBar = self.parent.statusBar()
        self.myFeatureProgressBar = QtGui.QProgressBar()
        self.myFeatureProgressBar.setMinimum(0)
        self.myFeatureProgressBar.setMaximum(numberOfJobs)
        self.myFeatureProgressBar.setFormat(' Features... %p%')
        statusBar.addWidget(self.myFeatureProgressBar)
        statusBar.show()
    
    def updateFeatureProgress(self):
        val = self.parent.project.featureMgr.getCount() 
        self.myFeatureProgressBar.setValue(val)
        if not self.parent.project.featureMgr.featureProcess.is_alive():
            self.myTimer.stop()
            self.terminateFeatureProgressBar()
            self.parent.project.featureMgr.joinCompute(self.parent.project.dataMgr)
            
    def terminateFeatureProgressBar(self):
        self.parent.statusBar().removeWidget(self.myFeatureProgressBar)
        self.parent.statusBar().hide()
        
    def featureShow(self, item):
        pass

class ClassificationTrain(object):
    def __init__(self, parent):
        self.parent = parent
        self.start()
        
    def start(self):               
        self.classificationTimer = QtCore.QTimer()
        self.parent.connect(self.classificationTimer, QtCore.SIGNAL("timeout()"), self.updateClassificationProgress)      
        numberOfJobs = 10                 
        self.initClassificationProgress(numberOfJobs)
        
        # Get Train Data
        
        #tic = time.clock()
        #self.parent.generateTrainingData()
        #Fc = self.parent.project.trainingMatrix
        #Lc = self.parent.project.trainingLabels
        #print "old time %f " % (time.clock() - tic)
        
        
        
        
        
        self.parent.labelWidget.updateLabelsOfDataItems(self.parent.project.dataMgr)
        tic2 = time.clock()
        #Nathan says: Fname is not used anywhere, so we do not need it? It does not work otherwise ...
        F,L,Fname = self.parent.project.dataMgr.buildTrainingMatrix()
        #F,L = self.parent.project.dataMgr.buildTrainingMatrix()
        print "new time %f " % (time.clock() - tic2)
        
        featLabelTupel = queue()
        featLabelTupel.put((F, L))
       
        self.classificationProcess = classificationMgr.ClassifierTrainThread(numberOfJobs, featLabelTupel)
        self.classificationProcess.start()
        self.classificationTimer.start(500) 

    def initClassificationProgress(self, numberOfJobs):
        statusBar = self.parent.statusBar()
        self.myClassificationProgressBar = QtGui.QProgressBar()
        self.myClassificationProgressBar.setMinimum(0)
        self.myClassificationProgressBar.setMaximum(numberOfJobs)
        self.myClassificationProgressBar.setFormat(' Training... %p%')
        statusBar.addWidget(self.myClassificationProgressBar)
        statusBar.show()
    
    def updateClassificationProgress(self):
        val = self.classificationProcess.count
        self.myClassificationProgressBar.setValue(val)
        if not self.classificationProcess.is_alive():
            self.classificationTimer.stop()
            self.classificationProcess.join()
            self.finalize()
            self.terminateClassificationProgressBar()
            
    def finalize(self):
        self.parent.project.classifierList = self.classificationProcess.classifierList
                      
    def terminateClassificationProgressBar(self):
        self.parent.statusBar().removeWidget(self.myClassificationProgressBar)
        self.parent.statusBar().hide()

class ClassificationInteractive(object):
    def __init__(self, parent):
        self.parent = parent
        self.stopped = False
        self.trainingQueue = deque(maxlen=1)

        self.parent.labelWidget.connect(self.parent.labelWidget, QtCore.SIGNAL('newLabelsPending'), self.updateTrainingQueue)
        self.interactiveTimer = QtCore.QTimer()
        self.parent.connect(self.interactiveTimer, QtCore.SIGNAL("timeout()"), self.updateLabelWidget)      
        self.temp_cnt = 0
        self.start()
        self.interactiveTimer.start(200)
        self.parent.labelWidget.cmbOverlayList.setCurrentIndex(1)
        
    def updateTrainingQueue(self):
        self.parent.generateTrainingData()
        F = self.parent.project.trainingMatrix
        L = self.parent.project.trainingLabels   

        self.trainingQueue.append((F, L))

    def updateLabelWidget(self):  
        predictIndex = self.parent.labelWidget.activeImage
        displayClassNr = self.parent.labelWidget.activeLabel  

        viewPredictions = {}
        for i, predict in irange(self.classificationInteractive.result):
            try:
                viewPredictions[i] = predict.pop()
            except IndexError:
                pass

        print "+++clock+++("
        self.parent.labelWidget.OverlayMgr.updatePredictionsPixmaps(viewPredictions)
        self.parent.labelWidget.OverlayMgr.setOverlayStateByIndex(self.parent.labelWidget.cmbOverlayList.currentIndex())
        print "+++clock+++)"
        # update Data Mgr
        for k in viewPredictions:
            self.parent.project.dataMgr.prediction[k] = viewPredictions[k]


    def initInteractiveProgressBar(self):
        statusBar = self.parent.statusBar()
        self.myInteractionProgressBar = QtGui.QProgressBar()
        self.myInteractionProgressBar.setMinimum(0)
        self.myInteractionProgressBar.setMaximum(0)
        statusBar.addWidget(self.myInteractionProgressBar)
        statusBar.show()
        
    def terminateClassificationProgressBar(self):
        self.parent.statusBar().removeWidget(self.myInteractionProgressBar)
        self.parent.statusBar().hide()
        
    def start(self):
        
        F = self.parent.project.trainingMatrix
        L = self.parent.project.trainingLabels
        
        self.trainingQueue.append((F, L))
        
        # [Todo: only do it once]
        predictDataList = self.parent.project.dataMgr.buildFeatureMatrix()      
        
        numberOfClasses = len(self.parent.project.labelNames)
        numberOfClassifiers = 6
        treeCount = 6
        self.classificationInteractive = classificationMgr.ClassifierInteractiveThread(self.trainingQueue, predictDataList, self.parent.labelWidget, numberOfClasses, numberOfClassifiers, treeCount)
        self.initInteractiveProgressBar()
               
        self.classificationInteractive.start()
    def stop(self):
        self.interactiveTimer.stop()
        self.classificationInteractive.stopped = True
        
        self.classificationInteractive.join()
        self.finalize()
        
        self.terminateClassificationProgressBar()
    
    def finalize(self):
        self.parent.project.classifierList = list(self.classificationInteractive.classifierList)
        
        self.classificationInteractive.finishPredictions()
        
        self.parent.project.dataMgr.prediction = map(lambda x:x.pop(), self.classificationInteractive.result)
        self.parent.labelWidget.OverlayMgr.updatePredictionsPixmaps(dict(irange(self.parent.project.dataMgr.prediction)))
        
class ClassificationOnline(object):
    def __init__(self, parent):
        print "Online Classification initialized"
        self.parent = parent
        
        self.OnlineThread = None
        self.parent.labelWidget.connect(self.parent.labelWidget, QtCore.SIGNAL('newLabelsPending'), self.updateTrainingData)
        self.parent.connect(self.parent, QtCore.SIGNAL('newPredictionsPending'), self.updatePredictionData)

    def __del__(self):
        self.parent.labelWidget.disconnect(self.parent.labelWidget, QtCore.SIGNAL('newLabelsPending'))
        self.parent.disconnect(self.parent,self.QtCore.SIGNAL('newPredictionsPending'))
        
    def start(self,name):
        print "Online Classification starting"

        self.parent.generateTrainingData()
        
        features = self.parent.project.trainingMatrix
        labels = self.parent.project.trainingLabels  

        self.parent.labelWidget.labelForImage[0].DrawManagers[0].createBrushQueue('onlineLearning')
        predictionList = self.parent.project.dataMgr.buildFeatureMatrix()
        ids = numpy.zeros((len(labels),)).astype(numpy.int32)

        self.OnlineThread = classificationMgr.ClassifierOnlineThread(name, features, labels.astype(numpy.int32), ids, predictionList, self.predictionUpdatedCallBack)
        self.OnlineThread.start()
        
    def stop(self):
        print "Online Classification stopped"
        self.OnlineThread.stopped = True
        self.OnlineThread.commandQueue.put((None, None, None, 'stop'))
        print "Joining thread"
        self.OnlineThread.join()
        print "Thread stopped"
        self.OnlineThread = None
        self.parent.labelWidget.labelForImage[0].DrawManagers[0].deleteBrushQueue('onlineLearning')
    
    def predictionUpdatedCallBack(self):
        self.parent.emit(QtCore.SIGNAL('newPredictionsPending'))

    def updatePredictionData(self):
        print "Updating prediction data"
        tic = time.time()
        if self.OnlineThread == None:
            return
        new_pred=self.OnlineThread.predictions[self.parent.labelWidget.activeImage].pop()
        #self.preds=numpy.zeros((new_pred.shape[0],2))
        #for i in xrange(len(new_pred)):
        #    self.preds[i,0]=1.0-new_pred[i]
        #    self.preds[i,1]=new_pred[i]
        print new_pred.shape

        tmp = {}
        print new_pred.shape
        tmp[self.parent.labelWidget.activeImage] = new_pred
        self.parent.labelWidget.OverlayMgr.updatePredictionsPixmaps(tmp)
        self.parent.labelWidget.OverlayMgr.setOverlayState('Prediction')
        
        
        print "Done updating prediction data: %f secs" % (time.time() - tic)
        #self.parent.labelWidget.OverlayMgr.showOverlayPixmapByState()
        
    
    def updateTrainingData(self):
        active_image=self.parent.labelWidget.activeImage
        print active_image
        Labels=self.parent.labelWidget.labelForImage[active_image].DrawManagers[0].labelmngr.labelArray
        queue=self.parent.labelWidget.labelForImage[active_image].DrawManagers[0].BrushQueues['onlineLearning']

        #TODO: make as many as there are images
        labelArrays=[numpy.array([0])] * (active_image+1)

        while(True):
            labelArrays[active_image]=numpy.zeros(Labels.shape,Labels.dtype)
            try:
                step=queue.pop()
            except IndexError:
                break
            #decompose step, start by removing data
            remove_data=[]

            for i in xrange(len(step.oldValues)):
                if step.oldValues[i]!=0 or step.isUndo:
                    remove_data.append(step.positions[i])
            remove_data=numpy.array(remove_data).astype(numpy.float32)
            self.OnlineThread.commandQueue.put((None,None,remove_data,'remove'))

            #add new data
            add_indexes=[]
            for i in xrange(len(step.oldValues)):
                if (not step.isUndo and step.newLabel!=0) or (step.isUndo and step.oldValues[i]!=0): 
                    add_indexes.append(step.positions[i])
                    labelArrays[active_image][step.positions[i]]=Labels[step.positions[i]]
            #create the new features
            self.parent.generateTrainingData(labelArrays)
            add_indexes=numpy.array(add_indexes)

            print "*************************************"
            print "************* SENDING ***************"
            print "*************************************"
            self.OnlineThread.commandQueue.put((self.parent.project.trainingMatrix,
                                                self.parent.project.trainingLabels.astype(numpy.int32),
                                                numpy.array(add_indexes).astype(numpy.int32),'learn'))
        
    
class ClassificationPredict(object):
    def __init__(self, parent):
        self.parent = parent
        self.start()
    
    def start(self):               
        self.classificationTimer = QtCore.QTimer()
        self.parent.connect(self.classificationTimer, QtCore.SIGNAL("timeout()"), self.updateClassificationProgress)      
        
        self.featureQueue = self.parent.project.dataMgr.buildFeatureMatrix()
        
        numberOfJobs = len(self.featureQueue) * len(self.parent.project.classifierList)
        
        self.initClassificationProgress(numberOfJobs)
        self.classificationPredict = classificationMgr.ClassifierPredictThread(self.parent.project.classifierList, self.featureQueue)
        self.classificationPredict.start()
        self.classificationTimer.start(200) 

    def initClassificationProgress(self, numberOfJobs):
        statusBar = self.parent.statusBar()
        self.myClassificationProgressBar = QtGui.QProgressBar()
        self.myClassificationProgressBar.setMinimum(0)
        self.myClassificationProgressBar.setMaximum(numberOfJobs)
        self.myClassificationProgressBar.setFormat(' Prediction... %p%')
        statusBar.addWidget(self.myClassificationProgressBar)
        statusBar.show()
    
    def updateClassificationProgress(self):
        val = self.classificationPredict.count
        self.myClassificationProgressBar.setValue(val)
        if not self.classificationPredict.is_alive():
            self.classificationTimer.stop()

            self.classificationPredict.join()
            self.finalize()           
            self.terminateClassificationProgressBar()

            displayImage = self.parent.labelWidget.activeImage
            predictions = dict(irange(self.classificationPredict.predictionList))
            self.parent.labelWidget.OverlayMgr.updatePredictionsPixmaps(predictions)
            self.parent.labelWidget.OverlayMgr.showOverlayPixmapByState()
            
    def finalize(self):
        self.parent.project.dataMgr.prediction = self.classificationPredict.predictionList
        
    def terminateClassificationProgressBar(self):
        self.parent.statusBar().removeWidget(self.myClassificationProgressBar)
        self.parent.statusBar().hide()


if __name__ == "__main__":
    app = QtGui.QApplication(sys.argv)
    mainwindow = MainWindow()  
    mainwindow.show() 
    app.exec_()
