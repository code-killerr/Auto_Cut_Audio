from .HandleAudio import HandleAudio
import os
import more_itertools
'''
# 待办 
    去除音频静音段底噪
    声道分离
'''


# 快捷操作函数

# 自动切割音频
def auto_cut_audio(audio_path, **kwargs):
    audio = HandleAudio(audio_path, **kwargs)
    return audio.autoSplitAudio()


# 根据音频时间段手动切割音频
def cut_audio(audio_path, save_path, cut_time_list):
    """
    :param audio_path: Str 音频路径
    :param save_path: str 音频存储路径
    :param cut_time_list: list 音频切割时长列表
    [[start,end],[start,end],......]
    :return: none
    """
    audio = HandleAudio(audio_path)
    for count, cut_time in enumerate(cut_time_list):
        save = create_cut_time(audio_path, count, cut_time[0], cut_time[1])
        save = os.path.join(save_path, save)
        audio.splitAudio(save, cut_time[0], cut_time[1])



# 获取音频前后静音段时长
def get_audio_front_and_end_empty_second(audio_path, voice_db=None):
    audio = HandleAudio(audio_path)
    start, end = audio.getFrontAndEndEmptySec(voice_db)
    return start, end

# 删除前后静音段
def get_audio_front_and_end_empty_second(audio_path, voice_db=None):
    audio = HandleAudio(audio_path)
    start, end = audio.getFrontAndEndEmptySec(voice_db)
    savePath = create_cut_time(audio_path, 0, start, end)
    savePath = os.path.join(os.path.dirname(audio_path), savePath)
    audio.splitAudio(savePath, start, end)
    return start, end

# 获取音频信息
def get_audio_info(audio_path):
    return HandleAudio(audio_path).getFmt()


# 限定时长自动切割音频
def auto_cut_audio_with_time(audio_path, limit_time, **kwargs):
    audio = HandleAudio(audio_path, emptySecond=99999, changeSecond=limit_time, **kwargs)
    return audio.autoSplitAudio()


# 自动切割音频并去除其中静音段
def auto_cut_audio_delete_empty_audio(audio_path, **kwargs):
    audio = HandleAudio(audio_path, **kwargs)
    return audio.autoSplitAudio(saveSlient=False)


# 自动切割音频不单独切出静音段
def auto_cut_audio_without_empty_audio(audio_path, **kwargs):
    audio = HandleAudio(audio_path, minSilentTime=99999, **kwargs)
    return audio.autoSplitAudio()


# 生成音频名称
def create_cut_time(audio_path, count, start, end):
    return f'{os.path.basename(audio_path)}_{count}_{str(start)}_{str(end)}'