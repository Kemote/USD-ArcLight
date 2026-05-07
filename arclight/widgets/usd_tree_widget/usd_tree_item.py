class UsdTreeItem:
    def __init__(self, item_data, parent_item=None):
        self.item_data = item_data
        self.parent_item = parent_item
        self.child_items = []

    @property
    def prim_stack(self):
        stack_list = []
        stack = self.item_data[2]
        for prim in stack:
            layer_path = prim.layer.realPath
            prim_path = prim.path
            prim_spec = prim.specifier
            stack_list.append([layer_path, prim_path, prim_spec])
        return stack_list

    def append_child(self, child):
        self.child_items.append(child)

    def child(self, row):
        return self.child_items[row]
    
    def child_count(self):
        return len(self.child_items)
    
    def row(self):
        if self.parent_item:
            return self.parent_item.child_items.index(self)
        