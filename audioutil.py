# -*- coding: UTF-8 -*-

'''
Author: CK
Date: 2020/11/18 16:55
Short Description: 

Change History:

三步走计划：1.先根据时间段，差值确定判断单位 2.手动调整合适参数 3.在有更高精准度要求的情况下进行训练
训练计划1.首先进行测试脚本编写，采用单音频进行监督学习测试，校验测试。2.测试成功后进行多组数据测试，取得合适的时间长度和差值

'''
'''
两个特征，一维数据，特征为截取时间段以及前一时间段和后一时间段之间的差值，找寻合适的截取时间和差值判断是否有人说话的时间段，校验取校验数据和机器判断数据之间的接近程度，注意防止过拟合
截取时间越短，导致判断差值越小，会导致判断数据小于校验数据，截取时间越大，导致判断差值越大，会导致判断数据导致大于校验数据
需要取到截取时间和差值之间的平衡点
选择大概区间，取得校验数据，做监督学习，找到取值最合适的值，采用先粗后细的多次校验来快速找到合适的值，时间差值先按照1s,0.1s,0.01s,分贝差值按照10db,1bd,0.1db,0,01db选择精确值
'''
'''
author:CK
自动判断是否说话，记录一段时间音频的最大值与另一段时间音频最大值做对比，如果差值过大判断为说话，问题为如何确定差值以及记录时间长短
自动判断切分分贝，取平均数值，再适当降低数值调整作为底噪声线。
introduce:按静音段切分音频

分为三段 S-M-E
S:只负责开头静音段的判别
S判断cut + mute
M判断cut + mute*2
E判断cut + mute
S切为 S->e-mute
M切为 S->e+mute e+mute->i-mute
E切为 S->e+mute e+mute -> i / S->i
end用来记录静音段开始位置，start用来记录切割段开始位置，i用来记录当前指向位置
startFlag 用来标记是否开始阶段，saveCount 标记存储序号
优化:
    按照静音时间，如果cut+mute*2>静音时间>mute*2 切为S->E+静音时间/2，更新位置M
    更新后必须设置留白时间，否则切割会出现问题
    
    
待优化:由于切割位置有可能为奇数位置导致双声道的音频左右声道互换，需要进行补足处理，防止双声道互换，激活方式应获取音频声道数，增加获取声道数方法，目前单声道无bug
'''
import math
import array
import os
import sys
import numpy
from collections import namedtuple
import struct




class handleAudio:
    # audioPath 音频文件路径
    # saveFolder 切割文件存储路径
    # emptySecond 音频静音时长超过emptySecond*2后切割音频/音频前后最少留白，设定为99999,可进行对切割出的音频时长通过changeSecond设定
    # emptySecond2 超过设定时长后,音频静音时长超过emptySecond2*2后切割音频/超过设定时长后音频前后最少留白
    # changeSecond 设定emptySecond参数变更时长设定,设定为99999,取消动态切割
    # limitDB 设定静音段分贝,如果为None将自动匹配底噪分贝(需背景音仅为底噪)
    # minSilentTime 切割出空白音频最小时间，设定时长为99999将不切分空白音频
    # 时长单位均为s,音量单位均为DB

    def __init__(self, audioPath, saveFolder=None, limitDB=None, emptySecond=0.5, emptySecond2=0.3, minSilentTime=1.0,
                 changeSecond=25):
        self.audioPath = audioPath
        self.audioHeader, self.audioData, self.headerBinary = self.__getHeaderAndData__(audioPath)
        self.fmt = self.__decodeFmt__(self.headerBinary)
        self.hz = self.fmt["hz"]
        self.channel = self.fmt["channel"]
        self.wavName = os.path.split(audioPath)[1].split('.wav')[0]
        self.dataLength = self.__len__()
        self.saveFolder = saveFolder
        # 前后留白时间 s
        self.emptySecond = emptySecond
        self.emptySecond2 = emptySecond2
        self.buf = None
        # 最小间隔时间 s
        self.minSilentTime = minSilentTime
        # 动态调整长度
        self.ChangeSecond = changeSecond
        self.noiseDB = self.__DBToValue__(limitDB)

    def setSaveFolder(self, path):
        self.saveFolder = path
    #设置噪声分贝，无参数贼采用自动分贝
    def setNoiseDB(self, limitDB):
        if limitDB is None:
            self.noiseDB = self.__getAutoSplitValue__()
        else:
            self.noiseDB = self.__DBToValue__(limitDB)

    def setEmptySecond(self, second):
        self.emptySecond = second

    def setEmptySecond2(self, second):
        self.emptySecond2 = second

    def setMinSilentTime(self, minTime):
        self.minSilentTime = minTime

    def setChangeSecond(self, second):
        self.ChangeSecond = second
    #如果未设置分贝将获取自动底噪分贝
    
    def getNoiseDB(self, useAmplitude=False):
        value = self.__getClearValue__(useAmplitude=useAmplitude)

        return self.__valueToDB__(value)
        # return self.noiseDB
    def getFmt(self):
        return self.fmt
    
    def getHz(self):
        return self.hz

    def getChannel(self):
        return self.channel

    # 获取前后静音段时间，如无分贝数自动按照振幅选取合适的底噪分贝，如有分贝数按照分贝数判断，如果背景有其它说话声音不要使用自动底噪判别
    def getFrontAndEndEmptySec(self, limitDB=None, useAmplitude = False):
        buf = self.__getAudioBuf__()
        hz = self.hz
        bufLength = self.dataLength
        if limitDB == None:
            voiceValue = self.__getClearValue__(useAmplitude)
        else:
            voiceValue = limitDB
        headerEmptySec = 0
        endEmptySec = 0
        for count in range(bufLength):
            if abs(buf[count]) > voiceValue:
                headerEmptySec = count / hz
                break
        for count in range(bufLength - 1, 0, -1):
            if abs(buf[count]) > voiceValue:
                endEmptySec = (bufLength - count) / hz
                break
        return headerEmptySec, endEmptySec
    
    # 手动切割音频方法
    def splitAudio(self, saveFile, start, end):
        self.__splitDataAndSaveAudio__(saveFile, int(start * self.hz * self.channel), int(end * self.hz * self.channel))

    # 自动切割音频方法
    def autoSplitAudio(self, save=None, value=None, saveSplitAudio=True, saveSlient=True, useAmplitude=False):
        if value is None:
            value = self.__getClearValue__(useAmplitude)
        if saveSplitAudio:
            if not save:
                if not self.saveFolder:
                    raise Exception("请设定切割文件存储路径")
                save = self.saveFolder
            if not os.path.isdir(save):
                raise Exception("文件切割路径错误: " + save)
        splitTimeData = []
        buf = self.__getAudioBuf__()
        n = self.dataLength
        hz = self.hz
        if n != len(buf):
            print("当前数据长度与header信息不符!!!!")
            print(n)
            print(len(buf))
            print(self.audioPath)
        clearSecond1 = int(hz * self.emptySecond * self.channel)
        clearSecond2 = int(hz * self.emptySecond2 * self.channel)
        cutSecond = int(hz * self.minSilentTime * self.channel)
        changeTime = hz * self.ChangeSecond * self.channel
        startFlag = True
        end = 0
        start = 0
        saveCount = 0
        # 切割分为三种状态,S,M,E
        for i in range(0, len(buf)):
            if startFlag:
                # 进入Start
                if abs(buf[i]) < value:
                    pass
                else:
                    # 开始录入切割部分并记录开始位置
                    if i - end > clearSecond1 + cutSecond:
                        end = i - clearSecond1
                        if saveSplitAudio and saveSlient:
                            if self.channel == 2:
                                end += 1 if end % 2 != 0 else 0
                            savePath = os.path.join(save,
                                                    f'{self.wavName}-{str(saveCount)}-{str(start / hz / self.channel)}-{str(end / hz / self.channel)}.wav')
                            self.__splitDataAndSaveAudio__(savePath, start, end)
                        if saveSlient:
                            splitTimeData.append([start / hz, end / hz])
                        start = end
                        saveCount += 1
                    end = i
                    # Start结束
                    startFlag = False
            else:
                # 进入Med
                if abs(buf[i]) > value:
                    # 动态调整
                    if end - start < changeTime:
                        clearSecond = clearSecond1
                    else:
                        clearSecond = clearSecond2
                    # 略微降低复杂度
                    if end + 1 != i and i - end > clearSecond * 2:
                        if i - end > clearSecond * 2 + cutSecond:
                            end = end + clearSecond
                            if saveSplitAudio:
                                if self.channel == 2:
                                    end += 1 if end % 2 != 0 else 0
                                savePath = os.path.join(save,
                                                        f'{self.wavName}-{str(saveCount)}-{str(start / hz / self.channel)}-{str(end / hz / self.channel)}.wav')
                                self.__splitDataAndSaveAudio__(savePath, start, end)
                            splitTimeData.append([start / hz, end / hz])
                            saveCount += 1
                            start = end
                            end = i - clearSecond
                            if saveSlient:
                                if saveSplitAudio:
                                    if self.channel == 2:
                                        end += 1 if end % 2 != 0 else 0
                                    savePath = os.path.join(save,
                                                            f'{self.wavName}-{str(saveCount)}-{str(start / hz / self.channel)}-{str(end / hz / self.channel)}.wav')
                                    self.__splitDataAndSaveAudio__(savePath, start, end)
                                splitTimeData.append([start / hz, end / hz])
                                saveCount += 1
                            start = end
                        else:
                            end = int(end + (i - end) / 2)
                            if saveSplitAudio:
                                if self.channel == 2:
                                    end += 1 if end % 2 != 0 else 0
                                savePath = os.path.join(save,
                                                        f'{self.wavName}-{str(saveCount)}-{str(start / hz / self.channel)}-{str(end / hz / self.channel)}.wav')
                                self.__splitDataAndSaveAudio__(savePath, start, end)
                            splitTimeData.append([start / hz, end / hz])
                            saveCount += 1
                            start = end
                    end = i
                else:
                    pass
        # 进入End
        clearSecond = clearSecond1
        if n - end > clearSecond + cutSecond:
            end = end + clearSecond
            if saveSplitAudio:
                if self.channel == 2:
                    end += 1 if end % 2 != 0 else 0
                savePath = os.path.join(save,
                                        f'{self.wavName}-{str(saveCount)}-{str(start / hz / self.channel)}-{str(end / hz / self.channel)}.wav')
                self.__splitDataAndSaveAudio__(savePath, start, end)
            splitTimeData.append([start / hz, end / hz])
            saveCount += 1
            start = end
            end = n
            if saveSlient:
                if saveSplitAudio:
                    if self.channel == 2:
                        end += 1 if end % 2 != 0 else 0
                    savePath = os.path.join(save,
                                            f'{self.wavName}-{str(saveCount)}-{str(start / hz / self.channel)}-{str(end / hz / self.channel)}.wav')
                    self.__splitDataAndSaveAudio__(savePath, start, end)
                splitTimeData.append([start / hz, end / hz])
                saveCount += 1
        else:
            end = n
            if saveSplitAudio:
                if self.channel == 2:
                    end += 1 if end % 2 != 0 else 0
                savePath = os.path.join(save,
                                        f'{self.wavName}-{str(saveCount)}-{str(start / hz / self.channel)}-{str(end / hz / self.channel)}.wav')
                self.__splitDataAndSaveAudio__(savePath, start, end)
            splitTimeData.append([start / hz, end / hz])
            saveCount += 1
        return splitTimeData

    '''
        #切割存储原始部分
        data = buf[startValue:i]
        #对于数据计数是以字节计数，一个buf占两个字节，需要计数i，
        len = (data.__len__()-1)*2
        dataLen = len.to_bytes(4,byteorder='little')
        fileLen = (len+header_bit).to_bytes(4,byteorder='little')
        header = info[0:4] + fileLen + info[8:40] + dataLen
        f2 = open(save+'\\'+str(saveCount)+'.wav', "wb")
        f2.write(header)
        data.tofile(f2)
        f2.close()
    '''

    # 获取数据长度
    def __len__(self):
        dataInfo = [x for x in self.audioHeader if x.id == b'data']
        if not dataInfo:
            raise Exception("Couldn't find data Length")
        dataInfo = dataInfo[0]
        pos = dataInfo.position + 4
        length = struct.unpack_from('<I', self.headerBinary[pos:pos + 4])[0]
        return int(length / 2)  # 音频数量两个字节为一个数值

    # 获取音频format数值
    def __decodeFmt__(self, data):
        fmt = [x for x in self.audioHeader if x.id == b'fmt ']
        # fmtIndex = self.__getDataFmtPlace__(self.audioHeader)
        # 获取各项属性值
        # hz = int.from_bytes(self.audioHeader[(fmtIndex + 12):(fmtIndex + 16)], byteorder='little', signed=True)
        # channel = int.from_bytes(self.audioHeader[(fmtIndex + 10):(fmtIndex + 12)], byteorder='little', signed=True)
        # audioFormat = int.from_bytes(self.audioHeader[(fmtIndex + 8):(fmtIndex + 10)], byteorder='little', signed=True)
        # byteRate = int.from_bytes(self.audioHeader[(fmtIndex + 16):(fmtIndex + 20)], byteorder='little', signed=True)
        # blockAlign = int.from_bytes(self.audioHeader[(fmtIndex + 20):(fmtIndex + 22)], byteorder='little', signed=True)
        # bps = int.from_bytes(self.audioHeader[(fmtIndex + 22):(fmtIndex + 24)], byteorder='little', signed=True)
        if not fmt or fmt[0].size < 16:
            raise Exception("Couldn't find fmt header in wav data")
        fmt = fmt[0]
        pos = fmt.position + 8  # 跳过fmt大小指示
        audio_format = struct.unpack_from('<H', data[pos:pos + 2])[0]
        if audio_format != 1 and audio_format != 0xFFFE:
            raise Exception("Unknown audio format 0x%X in wav data" %
                            audio_format)

        channels = struct.unpack_from('<H', data[pos + 2:pos + 4])[0]
        sample_rate = struct.unpack_from('<I', data[pos + 4:pos + 8])[0]
        byteRate = struct.unpack_from('<H', data[pos + 8:pos + 10])[0]
        blockAlign = struct.unpack_from('<H', data[pos + 12:pos + 14])[0]
        bits_per_sample = struct.unpack_from('<H', data[pos + 14:pos + 16])[0]
        return {"audioFormat": audio_format, "hz": sample_rate, "channel": channels, "byteRate": byteRate,
                "blockAlign": blockAlign, "bitsPerSample": bits_per_sample}

    def __splitDataAndSaveAudio__(self, savePath, start, end):
        header, data = self.__splitBufDataAndCreateDataHeader__(start, end)
        self.__saveBuf__(savePath, header, data)

    @staticmethod
    def __saveBuf__(path, header, data):

        f2 = open(path, "wb")
        f2.write(header)
        data.tofile(f2)
        f2.close()

    # 结尾和开始需要预留0.1不进行处理
    # 音频切割和存储
    def __splitBufDataAndCreateDataHeader__(self, startValue, end):
        info = self.headerBinary
        header_bit = len(self.headerBinary)
        buf = self.__getAudioBuf__()
        data = buf[startValue:end]
        # 对于数据计数是以字节计数，一个buf占两个字节，需要计数i，
        dataListLen = (data.__len__() - 1) * 2
        dataLen = dataListLen.to_bytes(4, byteorder='little')
        fileLen = (dataListLen + header_bit).to_bytes(4, byteorder='little')
        header = info[0:4] + fileLen + info[8:header_bit - 4] + dataLen

        return header, data

    # # 获取音频信息，data和音频头部信息
    # def __getAudioBufData__(self, source):
    #
    #     f = open(source, "rb")
    #
    #     infoData = f.read()
    #     try:
    #         # 读取数据头位置
    #         header_bit = self.__getDataStartPlace__(infoData)
    #         # 获取头数据
    #         f.seek(0)
    #         headerInfo = f.read(header_bit)
    #         # 读取fmt数据
    #
    #     except Exception as e:
    #         print("data error in " + source)
    #         raise Exception(e)
    #
    #     f.seek(header_bit - 4)  # 跳转至存储数据长度的位置
    #     n = int.from_bytes(f.read(4), byteorder='little', signed=True) // 2  # 获取数据长度，两字节模式读取，所以需要除2
    #     buf = array.array('h', (0 for x in range(n)))  # h为以2字节整型读取,使用0进行初始化
    #     # 获取音频数据
    #     f.seek(header_bit)
    #     f.readinto(buf)
    #     f.close()
    #     return buf, headerInfo

    # # 获取data开始位置
    # def __getDataStartPlace__(self, rbAudioData):
    #     dataWord = [100, 97, 116, 97]
    #     dataIndex = self.__compareBinaryDataPlace__(dataWord, rbAudioData)
    #     if dataIndex:
    #         header_bit = dataIndex + 8
    #         return header_bit
    #     else:
    #         raise Exception("can't find dataHeader")

    # 获取fmt开始位置
    # def __getDataFmtPlace__(self, rbAudioData):
    #     fmtWord = [102, 109, 116, 32]
    #     dataIndex = self.__compareBinaryDataPlace__(fmtWord, rbAudioData)
    #     if dataIndex:
    #         return dataIndex
    #     else:
    #         raise Exception("can't find FmtInfo")

    def __getAutoSplitDBByAmplitude__(self):
        # 根据最小振幅来判断噪声分贝
        buf = self.__getAudioBuf__()
        hz = self.hz
        bufLength = self.dataLength
        data = numpy.array(buf)
        if bufLength / hz > 1:
            getTime = abs((bufLength / hz) ** (1 / 7) - 1) * hz
        else:
            getTime = abs((bufLength / hz) ** 5) * hz
        if getTime < 10:
            print("音频时长过小，设置底噪值为默认")
            return self.__DBToValue__(50)
        cache = getTime
        minAmplitude = 99999
        noiseValue = 999999
        for i in range(int(cache), len(data - cache), int(getTime)):
            splitBuf = data[int(i - getTime):i]
            maxVoice = int(splitBuf.max())
            minVoice = int(splitBuf.min())
            amplitude = maxVoice - minVoice
            if amplitude > 0 and minVoice != 0 and amplitude < minAmplitude:
                minAmplitude = amplitude
                noiseValue = maxVoice
        # 转出来的自动值一般偏低，增加5分贝
        return self.__valueToDB__(noiseValue)

    #将数字转为长度为len的hash表内数据，方便插入
    #先除以len作为前置，再余len作为后置
    #返回hash表中位置以及存储的值
    # def __decodeAudioValue__(self, length, value):
    #     value = str(value)
    #     offset = len(str(length))
    #     frontData = int(value[:2])
    #     endData = int(value[2:])
    #
    #     return frontData, endData
    #
    # #将hash转换后数据所在的存储位置和值转为正常数据
    # def __encodeAudioValue__(self, length, pos, value):
    #     frontData = value * length
    #     encodeValue = frontData + pos
    #     return encodeValue
    #
    # # 使用跳跃查找找寻合适插入位置
    # def __insertValueToHash__(self, hashMap, pos, value):
    #     if hashMap[pos] == 0:
    #         hashMap[pos] = value

    def __insertValue__(self, valueList, value):
        length = len(valueList)
        left = 0
        right = length - 1
        mid = int(right / 2)
        while left <= right:
            if valueList[mid] > value:
                right = mid - 1
            else:
                left = mid + 1
            mid = int((right + left) / 2)
        valueList = numpy.insert(valueList, mid+1, value)
        # valueList.insert(mid + 1, value)
        valueList = numpy.delete(valueList, -1)
        # del valueList[-1]
        return valueList



    def __getAutoSplitValue__(self):
        # 根据最小分贝来判断噪声分贝
        buf = self.__getAudioBuf__()
        hz = self.hz
        bufLength = self.dataLength
        jumpTime = 0.001 * hz
        if bufLength / hz > 1:
            getTime = abs((bufLength / hz) ** (1 / 7) - 1) * hz
        else:
            print("音频时长过小，设置底噪值为默认")
            return self.__DBToValue__(50)
        if bufLength < getTime*6:
            print("音频时长过小，设置底噪值为默认")
            return self.__DBToValue__(50)
        audioSample = numpy.array([])
        # sortFlag = True
        countTime = 0
        timeSample = 0
        count = 0
        if bufLength != len(buf):
            print("当前数据长度与header信息不符!!!!")
            print(bufLength)
            print(len(buf))
            print(self.audioPath)
            bufLength = len(buf)
        # 防止数据被前后静音段影响,去除前后3个取值时间
        for i in range(int(getTime*3), int(bufLength-3*getTime), int(jumpTime)):
            sampleValue = abs(buf[i])
            if countTime > getTime:
                audioSample = numpy.append(audioSample, timeSample)
                countTime = 0
                count = 0
            if count != 0:
                timeSample = timeSample + (sampleValue - timeSample)/count
            else:
                timeSample = sampleValue
            countTime += jumpTime
            count += 1
            # if sampleValue < 1:
            #     continue
            # if sortFlag:
            #     if len(audioSample) < 100:
            #         audioSample = numpy.append(audioSample, sampleValue)
            #     else:
            #         audioSample.sort()
            #         sortFlag = False
            # else:
            #     audioSample = self.__insertValue__(audioSample, sampleValue)

        # noiseValue = audioSample.mean()
        audioSample.sort()
        noiseValue = audioSample[:1000].mean()

        return noiseValue

    def __getAudioBuf__(self):
        if self.buf is None:
            self.buf = array.array('h', self.audioData)
        return self.buf

    def __getClearValue__(self, useAmplitude):
        if self.noiseDB is None:
            if useAmplitude:
                self.noiseDB = self.__getAutoSplitDBByAmplitude__()
            else:
                self.noiseDB = self.__getAutoSplitValue__()

        return self.noiseDB

    # value转换为分贝
    @staticmethod
    def __valueToDB__(value):
        return math.log(value, 10) * 20

    # return 10 * log(value, 10) 使用功率作为value

    # 分贝转换
    @staticmethod
    def __DBToValue__(DB):
        if DB != None:
            return 10 ** (DB / 20)
        else:
            return None

    def __getHeaderAndData__(self, filePath):
        data = open(filePath, 'rb')
        dataBinary = data.read()
        chunks = self.__extract_wav_headers__(dataBinary)
        dataBuf = chunks[-1]
        if dataBuf.id != b'data':
            raise Exception("Couldn't find data in wav!!")

        pos = dataBuf.position + 8  # 去掉size段
        # struct.unpack_from 只去读设定格式的位数，后面就不读了
        # dataBuf = struct.unpack_from('<H', dataBinary[pos:(pos + dataBuf.size)])
        # dataBuf = array.array('h', dataBinary[pos:(pos + dataBuf.size)])
        headerBinary = dataBinary[:pos]
        data.close()
        return chunks, dataBinary[pos:(pos + dataBuf.size)], headerBinary

    # 获取所有文件节点信息
    def __extract_wav_headers__(self, data):
        # def search_subchunk(data, subchunk_id):
        WavSubChunk = namedtuple('WavSubChunk', ['id', 'position', 'size'])
        pos = 12  # The size of the RIFF chunk descriptor
        subchunks = []
        while pos + 8 <= len(data) and len(subchunks) < 10:
            subchunk_id = data[pos:pos + 4]
            subchunk_size = struct.unpack_from('<I', data[pos + 4:pos + 8])[0]
            subchunks.append(WavSubChunk(subchunk_id, pos, subchunk_size))
            if subchunk_id == b'data':
                # 'data' is the last subchunk
                break
            pos += subchunk_size + 8

        return subchunks

    # @staticmethod
    # # 找寻二进制信息点
    # def __compareBinaryDataPlace__(compareWord, binaryData):
    #     flag = False
    #     dataIndex = 0
    #     for i in range(len(binaryData)):
    #         wordcount = 0
    #         flag = True
    #         for j in compareWord:
    #             if binaryData[i + wordcount] == j:
    #                 wordcount += 1
    #                 pass
    #             else:
    #                 flag = False
    #                 break
    #         if flag:
    #             dataIndex = i
    #             break
    #     if flag == False:
    #         return False
    #     return dataIndex


def getAudioFrontAndEndEmptySec(audioPath, voiceDB=None):
    audio = handleAudio(audioPath)
    start, end = audio.getFrontAndEndEmptySec(voiceDB)
    return start, end


# if __name__ == '__main__':
# read_data(r'D:\workerFolder\work\project\solve_wav\00001-00400\00001.wav', r'D:\workerFolder\work\project\solve_wav\00001.wav')
# if __name__ == '__main__':
#     '''
#     if sys.argv.__len__() == 3:
#         sourceFolder = sys.argv[1]
#         saveFolder = sys.argv[2]
#     else:
#         print('invaild param(非法的参数数量)')
#         sys.exit(0)
#     '''
#
# start, end = getAudioFrontAndEndEmptySec(r'G:\20201130-Iris-Video\蓝色大海的传说\01BSEA\aaa.wav')
# print(start, end)
#     saveFolder = r'D:\workerFolder\work\project\新加坡音频处理\ASR\result4'
#     wavFolder = r'D:\workerFolder\work\project\新加坡音频处理\ASR\test3'
#     pathList = os.listdir(wavFolder)
#     for file in pathList:
#         os.makedirs(os.path.join(saveFolder, file.replace('.wav', '')))
#         audio = handleAudio(os.path.join(wavFolder, file), os.path.join(saveFolder, file.replace('.wav', '')), emptySecond2=0.05, changeSecond=20, emptySecond=0.75, minSilentTime=1.5)
#         autoValue = audio.getNoiseDB()+15
#         audio.setLimitDb(autoValue)
#         print(autoValue)
#         print(audio.getNoiseDB())
#         audio.autoSplitAudio()
    # audio.autoSplitAudio(r'D:\workerFolder\work\project\solve_wav\autocut\test')
# audio.autoSplitAudio(r'D:\workerFolder\work\project\solve_wav\OneDrive_1_2020-5-11\result')
# print(audio.__getAutoSplitValue__())
# audio.setEmptySecond(0.3)
# audio.setEmptySecond2(0.2)
# splitData = audio.splitAudio(r'D:\workerFolder\work\project\solve_wav\cut_wav15S\splitTest', saveSplitAudio=False)
# print(splitData)
