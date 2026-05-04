import os
from pxr import Usd


def open_stage(path):
    stage = None
    if os.path.exists(path):
        stage = Usd.Stage.Open(path)
    return stage
