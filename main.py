import PySimpleGUI as sg

layout = [
    [
        sg.Text("镜像：", size=(10, 1)),
        sg.Input(size=(33, 1)),
        sg.Button("刷新", size=(4, 1)),
    ],
    [
        sg.Text("版本：", size=(10, 1)),
        sg.Combo([], size=(40, 1)),
    ],
    [
        sg.Text("安装目录：", size=(10, 1)),
        sg.Input(size=(33, 1)),
        sg.Button("...", size=(4, 1)),
    ],
    [sg.vtop(sg.Text("忽略：", size=(10, 1))), sg.Multiline(size=(40, 8))],
    [sg.Button("开始安装", size=(51, 2))],
]

window = sg.Window("arknights-mower updater", layout)

event, values = window.read()

window.close()
