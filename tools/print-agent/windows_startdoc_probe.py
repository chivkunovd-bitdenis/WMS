"""WMS-762: what does the real pywin32 StartDoc return on Windows?"""
import os
import sys
import tempfile

import win32print
import win32ui
from PIL import Image, ImageWin

NAME = "Microsoft Print to PDF"


def main():
    print("python", sys.version)
    import win32api
    print("pywin32 build", win32api.GetFileVersionInfo(win32ui.__file__, "\\")["FileVersionLS"] if False else "n/a")
    flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    names = [record[2] for record in win32print.EnumPrinters(flags)]
    print("printers:", names)
    if NAME not in names:
        print("NO_PRINT_TO_PDF")
        return 3
    out = os.path.join(tempfile.mkdtemp(), "probe.pdf")
    dc = win32ui.CreateDC()
    dc.CreatePrinterDC(NAME)
    try:
        value = dc.StartDoc("WMS-762 probe", out)
        print("StartDoc returned type=%s repr=%r" % (type(value).__name__, value))
        dc.StartPage()
        image = Image.new("RGB", (200, 100), "black")
        ImageWin.Dib(image).draw(dc.GetHandleOutput(), (0, 0, 400, 200))
        dc.EndPage()
        end = dc.EndDoc()
        print("EndDoc returned type=%s repr=%r" % (type(end).__name__, end))
    finally:
        dc.DeleteDC()
    size = os.path.getsize(out) if os.path.exists(out) else -1
    print("pdf size", size)
    return 0 if size > 0 else 4


if __name__ == "__main__":
    raise SystemExit(main())
