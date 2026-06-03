import os
from pxr import Usd, UsdUtils


def open_stage(path):
    stage = None
    if os.path.exists(path):
        with Usd.StageCacheContext(UsdUtils.StageCache.Get()):
            stage = Usd.Stage.Open(path)
    return stage


def get_prim_compostion_data(prim: Usd.Prim):
    prim_query = Usd.PrimCompositionQuery(prim)
    arcs = prim_query.GetCompositionArcs()
    for arc in arcs:
        yield PrimStackInfo(arc)
        
    # root_node = prim_index.rootNode
    # layer_stack = root_node.layerStack
    # for layer in layer_stack.layers:
    #     usd_layer = Usd.Stage.Open(layer)
    #     prim_path = prim.GetPrimPath()
    #     layer_prim = usd_layer.GetPrimAtPath(prim_path)
    #     # layer prim to poodobno prim spec sprawdz to!!!
    #     if layer_prim:
    #         layer_index = layer_prim.GetPrimIndex()
    #         arc = layer_index
    #         print(arc.rootNode.arcType.name)


class PrimStackInfo:
    def __init__(self, arc):
        self.arc_type = arc.GetArcType()
        self.intro_layer = arc.GetIntroducingLayer()
        self.intro_prim = arc.GetIntroducingPrimPath()
        self.is_implicit = arc.IsImplicit()