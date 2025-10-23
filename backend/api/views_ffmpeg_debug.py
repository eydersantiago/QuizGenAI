# api/views_ffmpeg_debug.py (temporal)
import subprocess, shutil
from django.http import JsonResponse
from pydub import AudioSegment

def ffmpeg_debug(request):
    path = getattr(AudioSegment, "converter", None)
    which = shutil.which("ffmpeg")
    try:
        out = subprocess.check_output([path or which or "ffmpeg", "-version"], stderr=subprocess.STDOUT, timeout=3)
        version = out.decode("utf-8", "ignore").splitlines()[0]
    except Exception as e:
        version = f"ERR: {e}"
    return JsonResponse({"ffmpeg_path_attr": path, "ffmpeg_which": which, "version": version})
