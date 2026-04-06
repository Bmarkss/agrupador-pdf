"""
AgrupadorPDF.py — Entry point do aplicativo.

Estrutura necessária na mesma pasta deste arquivo:
  agrupador/
    __init__.py
    config.py
    extractor.py
    grouper.py
    merger.py
    models.py
    ui/
      __init__.py
      app.py
      widgets.py
"""

import sys
import os

# Garante que a pasta do script está no path, independente de como foi chamado
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

try:
    from agrupador.ui.app import App
except Exception as _err:
    import traceback
    _tb = traceback.format_exc()
    try:
        import tkinter as tk
        from tkinter import messagebox
        _root = tk.Tk()
        _root.withdraw()
        messagebox.showerror(
            "AgrupadorPDF — Erro ao iniciar",
            f"Não foi possível carregar o aplicativo.\n\n"
            f"Verifique se a pasta 'agrupador' está no mesmo diretório "
            f"que este arquivo e se todos os arquivos estão presentes.\n\n"
            f"Detalhe técnico:\n{_tb}"
        )
        _root.destroy()
    except Exception:
        print(_tb)
    sys.exit(1)

if __name__ == "__main__":
    app = App()
    app.mainloop()
