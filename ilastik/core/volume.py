import numpy, vigra, h5py


"""
helper function to prevent the creation of endless deep DataAccessor chains
"""
def createDataAccessor( data, channels = False,  autoRgb = True):
        if issubclass(data.__class__,  DataAccessor):
            return data
        else:
            return DataAccessor(data, channels, autoRgb)


class DataAccessor():
    """
    This class gives consistent access to data volumes, images channels etc.
    access is always of the form [time, x, y, z, channel]
    """
    
    def __init__(self, data, channels = False,  autoRgb = True):
        """
        data should be a numpy/vigra array that transformed to the [time, x, y, z, channel] access like this:
            1d: (a,b), b != 3 and channels = False  (0,0,a,b,0)
            1d: (a,b), b == 3 or channels = True:  (0,0,0,a,b)
            2d: (a,b,c), c != 3 and channels = False:  (0,a,b,c,0)
            2d: (a,b,c), c == 3 or channels = True:  (0,0,a,b,c)
            etc.
        """
        
        if issubclass(data.__class__,  DataAccessor):
            self.data = data.data
            self.rgb = data.rgb
            self.shape = data.shape
            self.dtype = data.dtype
        else:

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
            
            if len(self.data.shape) != 5:
                self.data = self.data.reshape(tempShape)
                
            self.channels = self.data.shape[-1]

            self.rgb = False
            if autoRgb:
                if data.shape[-1] == 3:
                    self.rgb = True

            self.shape = self.data.shape
            self.dtype = self.data.dtype


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
    def deserialize(h5G, name = 'data', offsets=(0, 0, 0), shape=(0, 0, 0)):
        if (h5G[name].value.shape[1]==1):
            #2d data
            if shape == (0,0,0):        
                data = h5G[name].value[:,:,offsets[0]:, offsets[1]:, :]
            else:
                data = h5G[name].value[:,:,offsets[0]:offsets[0]+shape[0], offsets[1]:offsets[1]+shape[1], :]
        else:
            #3 and more d data:
            if shape == (0,0,0):        
                data = h5G[name].value[:,offsets[0]:, offsets[1]:, offsets[2]:, :]
            else:
                data = h5G[name].value[:,offsets[0]:offsets[0]+shape[0], offsets[1]:offsets[1]+shape[1], offsets[2]:offsets[2]+shape[2],:]
        return DataAccessor(data, channels = True)
        
class VolumeLabelDescription():
    def __init__(self, name,number, color,  prediction):
        self.number = number
        self.name = name
        self.color = color
        self.prediction = prediction

        
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
        t = VolumeLabelDescription( self.name, self.number, self.color,  self.prediction)
        return t
    
class VolumeLabels():
    def __init__(self, data = None):
        if issubclass(data.__class__, DataAccessor):
            self.data = data
        else:
            self.data = DataAccessor(data, channels = False)
        self.history = None    #history of drawing operations
        self.descriptions = [] #array of VolumeLabelDescriptions
        
    def clear(self):
        #TODO: clear the labvles
        pass
        
    def serialize(self, h5G, name):
        group = h5G.create_group(name)
        self.data.serialize(group, 'data')
        
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
            
        if self.history is not None:
            self.history.serialize(group, 'history')        
            
    def getLabelNames(self):
        labelNames = []
        for idx, it in enumerate(self.descriptions):
            labelNames.append(it.name)
        return labelNames    
        
        
    def getColorTab(self):
        colorTab = []
        for i in range(256):
            colorTab.append(long(0)) #QtGui.QColor(0,0,0,0).rgba()

        for index,item in enumerate(self.descriptions):
            colorTab[item.number] = long(item.color)
        return colorTab
        
    @staticmethod    
    def deserialize(h5G, name ="labels", offsets = (0,0,0), shape=(0,0,0)):
        if name in h5G.keys():
            t = h5G[name]
            if isinstance(t,h5py.highlevel.Group):
                data = DataAccessor.deserialize(t, 'data', offsets, shape)
            else:
                data = DataAccessor.deserialize(h5G, name, offsets, shape)
            colors = []
            names = []
            numbers = []
            if h5G[name].attrs.__contains__('color'):
                colors = h5G[name].attrs['color']
                names = h5G[name].attrs['name']
                numbers = h5G[name].attrs['number']
            descriptions = []
            for index, item in enumerate(colors):
                descriptions.append(VolumeLabelDescription(names[index], numbers[index], colors[index],  numpy.zeros(data.shape[0:-1],  'uint8')))
    
            vl =  VolumeLabels(data)
            vl.descriptions = descriptions
            return vl
        else:
            return None
        
class Volume():
    def __init__(self,  data,  labels = None,  seeds = None,  uncertainty = None,  segmentation = None):
        self.data = data
        self.labels = labels
        self.seeds = seeds
        
        self.seedOverlays = []
        self.labelOverlays = []
        
        self.uncertainty = uncertainty
        self.segmentation = segmentation
        
        if self.labels is None:
            l = numpy.zeros(self.data.shape[0:-1] + (1, ),  'uint8')
            self.labels = VolumeLabels(l)
            
        if self.seeds is None:
            l = numpy.zeros(self.data.shape[0:-1] + (1, ),  'uint8')
            self.seeds = VolumeLabels(l)

        if self.uncertainty is None:
            self.uncertainty = numpy.zeros(self.data.shape[0:-1],  'uint8')

        if self.segmentation is None:
            self.segmentation = numpy.zeros(self.data.shape[0:-1],  'uint8')


    def serialize(self, h5G):
        self.data.serialize(h5G, "data")
        if self.labels is not None:
            self.labels.serialize(h5G, "labels")
        if self.seeds is not None:
            self.seeds.serialize(h5G, "seeds")
        
    @staticmethod
    def deserialize(h5G, offsets = (0,0,0), shape=(0,0,0)):
        #TODO: make nicer
        data = DataAccessor.deserialize(h5G, "data", offsets, shape)
        labels = VolumeLabels.deserialize(h5G, "labels",offsets, shape)
        seeds = VolumeLabels.deserialize(h5G,  "seeds")
        v =  Volume(data,  labels = labels,  seeds = seeds)
        return v


