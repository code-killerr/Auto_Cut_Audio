# Auto_Cut_Audio(wav for now)
We always have a lot of wav audio to cut.

sometimes we need to cut them but we always cut off a word or a complete sentence in audio.

now~ you won't.

## what I can do with this

### 1. auto cut audio 🧠

you can cut audio what you like,you can use auto_cut_audio to split your wav file, make sure
there will be a whole voice in a while without empty voice in it.

#### How to use
we have two ways for you to use it

this is a easy way to use it
```python
import auto_cut_audio
auto_cut_audio.auto_cut_audio(r'audio path',saveFolder=r'save folder')
```
if you just want to get cut time you can do it
```python
import auto_cut_audio
cut_time = auto_cut_audio.auto_cut_audio(r'audio path')
print(cut_time)
```

more function in the HandleAudio class

```python
import auto_cut_audio
audio = auto_cut_audio.HandleAudio(r'audio_path')
audio.autoSplitAudio()
```
if you find the cut audio is not very good

you can also change these param to make progress adjust your audio.

```python
audioPath: str
# 音频文件路径
saveFolder: str
# 切割文件存储路径
emptySecond: float
# 音频静音时长超过emptySecond*2后切割音频/音频前后最少留白，设定为99999,可进行对切割出的音频时长通过changeSecond设定
emptySecond2: float
# 超过设定时长后,音频静音时长超过emptySecond2*2后切割音频/超过设定时长后音频前后最少留白
changeSecond: float
# 设定静音段分贝,如果为None将自动匹配底噪分贝(需背景音仅为底噪)
limitDB: float
# 设定静音段分贝,如果为None将自动匹配底噪分贝(需背景音仅为底噪)
minSilentTime: float
# 切割出空白音频最小时间，设定时长为99999将不切分空白音频
```

### 2. cut audio😎

if you don't want to use auto cut,you can also cut your audio with time

```python
import auto_cut_audio
cut_time = [[0,12],[12,23],[23,30]]
auto_cut_audio.cut_audio('audio path', 'save folder', cut_time)
```
### 3. get audio info🤓

if you don't want to cut audio you just want to get some information with your audio file,you can do it

```python
import auto_cut_audio
auto_cut_audio.get_audio_info('audio path')
```

### 4. get slience time in audio start and end👌

if you want to know how many seconds have no voice in your audio file start and end,you can do it.

```python
import auto_cut_audio
auto_cut_audio.get_audio_front_and_end_empty_second('audio path')
```

and you can also delete them with cut audio

