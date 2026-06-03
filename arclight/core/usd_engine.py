import os
from pxr import Usd, UsdUtils


def open_layer(path):
    layer = None
    if os.path.exists(path):
        with Usd.StageCacheContext(UsdUtils.StageCache.Get()):
            layer = Usd.Stage.Open(path)
    return layer

def create_in_memmory_stage():
    return Usd.Stage.CreateInMemory()

def get_prim_compostion_data(prim: Usd.Prim):
    prim_query = Usd.PrimCompositionQuery(prim)
    arcs = prim_query.GetCompositionArcs()
    for arc in arcs:
        yield PrimStackInfo(arc)
        

class PrimStackInfo:
    def __init__(self, arc):
        self.arc_type = arc.GetArcType()
        self.intro_layer = arc.GetIntroducingLayer()
        self.intro_prim = arc.GetIntroducingPrimPath()
        self.is_implicit = arc.IsImplicit()