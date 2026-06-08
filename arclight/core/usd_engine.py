import os
from pxr import Usd, UsdUtils, Pcp


def open_layer(path):
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

def create_new_file(file_path):
    dir_name = os.path.dirname(file_path)
    if not os.path.exists(dir_name):
        os.makedirs(dir_name)
    new_file = Usd.Stage.CreateNew(file_path)
    new_file.Save()
    return file_path
        

class PrimStackInfo:
    def __init__(self, arc):
        self.arc_type = self._get_arc_type(arc)
        self.intro_layer = self._get_layer_real_path(arc)
        self.intro_prim = arc.GetIntroducingPrimPath()
        self.is_implicit = arc.IsImplicit()

    @staticmethod
    def _get_arc_type(arc):
        arc_type = arc.GetArcType()
        if arc_type == Pcp.ArcTypeRoot:
            return "Sublayer / Local"
        elif arc_type == Pcp.ArcTypeInherit:
            return "Inherit"
        elif arc_type == Pcp.ArcTypeVariant:
            return "Variant"
        elif arc_type == Pcp.ArcTypeReference:
            return "Reference"
        elif arc_type == Pcp.ArcTypePayload:
            return "Payload"
        elif arc_type == Pcp.ArcTypeSpecialize:
            return "Specializes"
        
    @staticmethod
    def _get_layer_real_path(arc):
        intro_layer = arc.GetIntroducingLayer()
        if intro_layer:
            return intro_layer.realPath
        else:
            return "annonymous layer"