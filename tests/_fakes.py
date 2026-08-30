"""Duck-typed stand-ins for KiCad objects used by the pure-logic tests."""


class FakeFpid:
    def __init__(self, name):
        self.name = name

    def GetLibItemName(self):
        return self.name

    def GetLibId(self):
        return self.name


class FakePad:
    def __init__(self, number, net_code, net_name="", net=None):
        self.number = number
        self.net_code = net_code
        self.net_name = net_name
        self.net = net

    def GetNumber(self):
        return self.number

    def GetNetCode(self):
        return self.net_code

    def GetNetname(self):
        return self.net_name

    def GetNet(self):
        return self.net


class FakeFootprint:
    def __init__(self, ref, value="10k", fp_name="R_0805", pads=None,
                 x=0, y=0, locked=False):
        self.ref = ref
        self.value = value
        self.fp_name = fp_name
        self.pads = pads if pads is not None else []
        self.x = x
        self.y = y
        self.locked = locked

    def GetReference(self):
        return self.ref

    def GetValue(self):
        return self.value

    def GetFPID(self):
        return FakeFpid(self.fp_name)

    def Pads(self):
        return self.pads

    def GetPosition(self):
        return (self.x, self.y)

    def IsLocked(self):
        return self.locked

    def GetSheetfile(self):
        return ""

    def GetSheetname(self):
        return ""

    def GetPath(self):
        return FakePath()


class FakePath:
    def AsString(self):
        return ""


class FakeBoard:
    def __init__(self, footprints):
        self.footprints = footprints

    def GetFootprints(self):
        return self.footprints
