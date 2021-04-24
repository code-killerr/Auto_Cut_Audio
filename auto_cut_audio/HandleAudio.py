# -*- coding: UTF-8 -*-

'''
Author: CK
Date: 2020/11/18 16:55
Short Description: 

Change History:
end用来记录静音段开始位置，start用来记录切割段开始位置，i用来记录当前指向位置
startFlag 用来标记是否开始阶段，saveCount 标记存储序号
更新:
    按照静音时间，如果cut+mute*2>静音时间>mute*2 切为S->E+静音时间/2，更新位置M
    可设定是否输出切割文件
    可设定底噪定位算法

'''
import math
import array
import os
import numpy
from collections import namedtuple
import struct

WavSubChunk = namedtuple('WavSubChunk', ['id', 'position', 'size'])


class HandleAudio:

    def __init__(self, audioPath, saveFolder=None, limitDB=None, emptySecond=0.5, emptySecond2=0.3, minSilentTime=1.0,
                 changeSecond=25):
        """
                @param audioPath: String
                音频文件路径
                @param saveFolder: String
                切割文件存储路径
                @param emptySecond: float
                音频静音时长超过emptySecond*2后切割音频/音频前后最少留白，设定为99999,可进行对切割出的音频时长通过changeSecond设定
                @param emptySecond2: float
                超过设定时长后,音频静音时长超过emptySecond2*2后切割音频/超过设定时长后音频前后最少留白
                @param changeSecond: float
                设定静音段分贝,如果为None将自动匹配底噪分贝(需背景音仅为底噪)
                @param limitDB: float
                设定静音段分贝,如果为None将自动匹配底噪分贝(需背景音仅为底噪)
                @param minSilentTime: float
                切割出空白音频最小时间，设定时长为99999将不切分空白音频

                时长单位均为s,音量单位均为DB
                @return: none
            """
        self.audioPath = audioPath
        self.audioHeader, self.audioData, self.headerBinary = self.__get_header_and_data__(audioPath)
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

    # 设置噪声分贝，无参数贼采用自动分贝
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

    # 如果未设置分贝将获取自动底噪分贝
    # 获取到的值统一为振幅高度
    def getNoiseDB(self, useAmplitude=False):
        value = self.__getClearValue__(useAmplitude=useAmplitude)

        return self.__valueToDB__(value)

    def getFmt(self):
        return self.fmt

    def getHz(self):
        return self.hz

    def getChannel(self):
        return self.channel

    # 获取前后静音段时间，如无分贝数自动按照振幅选取合适的底噪分贝，如有分贝数按照分贝数判断，如果背景有其它说话声音不要使用自动底噪判别
    def getFrontAndEndEmptySec(self, limitDB=None, useAmplitude=False):
        buf = self.__getAudioBuf__()
        hz = self.hz
        bufLength = self.dataLength
        if limitDB is None:
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
    def autoSplitAudio(self, save=None, value=None, saveSlient=True, useAmplitude=False):
        """
            @param save: String
            切割文件存储路径
            @param value: int
            底噪手动设定数值
            @param saveSlient: boolean
            设定是否存储静音段
            @return: list
            音频切割时间点信息
        """
        saveSplitAudio = True
        splitTimeData = []
        buf = self.__getAudioBuf__()
        n = self.dataLength

        if not value:
            value = self.__getClearValue__(useAmplitude)

        # 检测是否存在保存路径，无保存路径不保存切割后数据
        if save is None:
            if self.saveFolder is None:
                saveSplitAudio = False
            else:
                save = self.saveFolder
        # 判断路径有效
        if saveSplitAudio:
            if not os.path.isdir(save):
                raise Exception("文件切割路径错误: " + save)

        if n != len(buf):
            print("当前数据长度与header信息不符!!!!")
            print(n)
            print(len(buf))
            print(self.audioPath)
        clearSecond1 = int(self.hz * self.emptySecond * self.channel)
        clearSecond2 = int(self.hz * self.emptySecond2 * self.channel)
        cutSecond = int(self.hz * self.minSilentTime * self.channel)
        changeTime = self.hz * self.ChangeSecond * self.channel
        startFlag, end, start, saveCount = True, 0, 0, 0

        # 切割分为三种状态,S,M,E
        for i in range(0, len(buf)):
            if startFlag:
                # 进入Start
                if abs(buf[i]) >= value:
                    # 开始录入切割部分并记录开始位置
                    if i - end > clearSecond1 + cutSecond:
                        end = i - clearSecond1
                        if saveSplitAudio and saveSlient:
                            self.__saveWithChannels__(start, end, saveCount, save)
                        if saveSlient:
                            splitTimeData.append([start / self.hz, end / self.hz])
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
                                self.__saveWithChannels__(start, end, saveCount, save)
                            splitTimeData.append([start / self.hz, end / self.hz])
                            saveCount += 1
                            start = end
                            end = i - clearSecond
                            if saveSlient:
                                if saveSplitAudio:
                                    self.__saveWithChannels__(start, end, saveCount, save)
                                splitTimeData.append([start / self.hz, end / self.hz])
                                saveCount += 1
                            start = end
                        else:
                            end = int(end + (i - end) / 2)
                            if saveSplitAudio:
                                self.__saveWithChannels__(start, end, saveCount, save)
                            splitTimeData.append([start / self.hz, end / self.hz])
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
                self.__saveWithChannels__(start, end, saveCount, save)
            splitTimeData.append([start / self.hz, end / self.hz])
            saveCount += 1
            start = end
            end = n
            if saveSlient:
                if saveSplitAudio:
                    self.__saveWithChannels__(start, end, saveCount, save)
                splitTimeData.append([start / self.hz, end / self.hz])
                saveCount += 1
        else:
            end = n
            if saveSplitAudio:
                self.__saveWithChannels__(start, end, saveCount, save)
            splitTimeData.append([start / self.hz, end / self.hz])
            saveCount += 1
        return splitTimeData

    # 获取数据长度
    def __len__(self):
        dataInfo = [x for x in self.audioHeader if x.id == b'data']
        if not dataInfo:
            raise Exception("Couldn't find data Length")
        dataInfo = dataInfo[0]
        pos = dataInfo.position + 4
        length = struct.unpack_from('<I', self.headerBinary[pos:pos + 4])[0]
        return int(length / 2)  # 音频数量两个字节为一个数值

    def __saveWithChannels__(self, start, end, saveCount, save):
        if self.channel == 2:
            end += 1 if end % 2 != 0 else 0
        savePath = os.path.join(save,
                                f'{self.wavName}-{str(saveCount)}-{str(start / self.hz / self.channel)}-{str(end / self.hz / self.channel)}.wav')
        self.__splitDataAndSaveAudio__(savePath, start, end)

    # 获取音频format数值
    def __decodeFmt__(self, data):
        fmt = [x for x in self.audioHeader if x.id == b'fmt ']
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
        valueList = numpy.insert(valueList, mid + 1, value)
        # valueList.insert(mid + 1, value)
        valueList = numpy.delete(valueList, -1)
        # del valueList[-1]
        return valueList

    # 根据最小平均声音获取底噪 返回value(非分贝)
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
        if bufLength < getTime * 6:
            print("音频时长过小，设置底噪值为默认")
            return self.__DBToValue__(50)
        audioSample = numpy.array([])
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
        for i in range(int(getTime * 3), int(bufLength - 3 * getTime), int(jumpTime)):
            sampleValue = abs(buf[i])
            if countTime > getTime:
                audioSample = numpy.append(audioSample, timeSample)
                countTime = 0
                count = 0
            if count != 0:
                timeSample = timeSample + (sampleValue - timeSample) / count
            else:
                timeSample = sampleValue
            countTime += jumpTime
            count += 1

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
                # 根据声音判定会偏小，通常加15分贝微调
                self.__addDbInValue__(self.noiseDB, 15)

        return self.noiseDB

    # 在value的基础上增加相应分贝
    def __addDbInValue__(self, value, db):
        return self.__DBToValue__(self.__valueToDB__(value) + db)

    # value转换为分贝
    @staticmethod
    def __valueToDB__(value):
        return math.log(value, 10) * 20

    # 分贝转换
    @staticmethod
    def __DBToValue__(DB):
        if DB is not None:
            return 10 ** (DB / 20)
        else:
            return None

    # 获取头节点二进制数据
    def __extract_wav_headers__(self, data):
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

    # 获取所有文件节点信息
    def __get_header_and_data__(self, filePath):
        data = open(filePath, 'rb')
        dataBinary = data.read()
        chunks = self.__extract_wav_headers__(dataBinary)
        dataBuf = chunks[-1]
        if dataBuf.id != b'data':
            raise Exception("Couldn't find data in wav!!")

        pos = dataBuf.position + 8  # 去掉size段
        headerBinary = dataBinary[:pos]
        data.close()
        return chunks, dataBinary[pos:(pos + dataBuf.size)], headerBinary
