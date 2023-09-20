class Builder:
    def __init__(self, saveFolder=None, limitDB=None, emptySecond=0.5, emptySecond2=0.3, minSilentTime=1.0,
                 changeSecond=25):
        self.saveFolder = saveFolder
        self.limitDB = limitDB
        self.emptySecond = emptySecond
        self.emptySecond2 = emptySecond2
        self.minSilentTime = minSilentTime,
        self.changeSecond = changeSecond