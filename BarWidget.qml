import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

Panel {
    id: root
    moduleName: "io.github.adamtcroft.pipewire-control"
    ipcTarget: moduleName
    implicitWidth: button.implicitWidth
    implicitHeight: button.implicitHeight

    readonly property color foreground: bar ? bar.foreground : Color.foreground
    readonly property color dim: Qt.darker(foreground, 1.55)
    readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
    readonly property string helper: decodeURIComponent(Qt.resolvedUrl("control.py").toString().replace(/^file:\/\//, ""))
    property var info: ({settings: {}, devices: [], graph: [], saved: {}})
    property int chosenRate: 0
    property int chosenBuffer: 0
    property int defaultRate: 0
    property int defaultBuffer: 0
    property bool defaultsDirty: false
    property string pending: ""
    property int pendingRate: 0
    property int pendingBuffer: 0
    property string actionKind: ""
    property string message: ""
    property bool failed: false
    property bool initialized: false
    readonly property bool busy: action.running
    readonly property bool hasSavedDefaults: info.saved && Object.keys(info.saved).length > 0
    readonly property var device: info.devices.find(function(d) { return d.rates.length > 0 }) || (info.devices.length ? info.devices[0] : null)
    readonly property string activeRate: device && device.rates.length ? device.rates.map(function(r) { return (Number(r) / 1000) + " kHz" }).join(" / ") : "Idle"
    readonly property string validBits: device && device.bits.length ? device.bits.join(" / ") + "-bit" : "Unknown"

    function refresh() { if (!status.running) status.running = true }
    function settingValue(value) {
        var number = Number(value)
        return isFinite(number) && number >= 0 ? number : 0
    }
    function savedValue(key) {
        return settingValue((info.saved || {})[key])
    }
    function pairText(rate, buffer) {
        return (rate ? rate / 1000 + " kHz" : "Auto rate") + " · " + (buffer ? buffer + " samples" : "Auto buffer")
    }
    function request(kind) {
        if (busy || pending) return
        pending = kind
        pendingRate = kind === "apply" ? chosenRate : kind === "save" ? defaultRate : 0
        pendingBuffer = kind === "apply" ? chosenBuffer : kind === "save" ? defaultBuffer : 0
        message = ""
        failed = false
    }
    function execute() {
        if (!pending || busy) return
        var kind = pending
        var command = kind === "apply" || kind === "auto" ? "apply" : "save"
        var rate = pendingRate
        var buffer = pendingBuffer
        pending = ""
        actionKind = kind
        action.command = ["python3", helper, command, String(rate), String(buffer)]
        action.running = true
    }
    onOpenedChanged: {
        if (opened) {
            if (!defaultsDirty) {
                defaultRate = savedValue("rate")
                defaultBuffer = savedValue("quantum")
            }
            refresh()
        } else {
            pending = ""
        }
    }

    Process {
        id: status
        command: ["python3", root.helper, "json"]
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    root.info = JSON.parse(text)
                    if (!root.initialized) {
                        root.chosenRate = root.settingValue(root.info.settings["clock.force-rate"])
                        root.chosenBuffer = root.settingValue(root.info.settings["clock.force-quantum"])
                        root.initialized = true
                    }
                    if (!root.defaultsDirty) {
                        root.defaultRate = root.savedValue("rate")
                        root.defaultBuffer = root.savedValue("quantum")
                    }
                } catch (e) { root.message = "Could not read audio status."; root.failed = true }
            }
        }
        stderr: StdioCollector { onStreamFinished: if (text.trim()) { root.message = text.trim(); root.failed = true } }
    }
    Process {
        id: action
        stdout: StdioCollector { onStreamFinished: if (text.trim()) root.message = text.trim() }
        stderr: StdioCollector { onStreamFinished: if (text.trim()) { root.message = text.trim(); root.failed = true } }
        onExited: function(code) {
            var completed = root.actionKind
            root.failed = code !== 0
            if (code === 0 && (completed === "save" || completed === "remove")) root.defaultsDirty = false
            root.actionKind = ""
            root.refresh()
        }
    }
    Timer { interval: 5000; running: root.opened; repeat: true; onTriggered: root.refresh() }
    Component.onCompleted: refresh()

    BarIconButton {
        id: button
        anchors.fill: parent
        bar: root.bar
        tooltipText: "PipeWire Control"
        iconComponent: Component {
            AudioIcon { color: root.barForeground; size: Style.space(16) }
        }
        onPressed: function(b) { if (b === Qt.MiddleButton) root.refresh(); else if (b === Qt.LeftButton) root.toggle() }
    }

    KeyboardPanel {
        id: panel
        anchorItem: button
        owner: root
        bar: root.bar
        open: root.opened
        focusTarget: content
        contentWidth: panel.fittedContentWidth(Style.space(400))
        contentHeight: panel.fittedContentHeight(column.implicitHeight, Style.space(700))

        FocusScope {
            id: content
            anchors.fill: parent
            Keys.onEscapePressed: { if (root.pending) root.pending = ""; else root.close() }
            Flickable {
                anchors.fill: parent
                contentWidth: width
                contentHeight: column.implicitHeight
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                Column {
                    id: column
                    width: parent.width
                    spacing: Style.space(14)
                    PanelHero {
                        width: parent.width
                        title: "PipeWire Control"
                        foreground: root.foreground
                        fontFamily: root.fontFamily
                        iconComponent: Component { AudioIcon { color: root.foreground; size: Style.space(32) } }
                        trailingControl: Component {
                            PanelActionButton { iconText: "󰑐"; tooltipText: "Refresh status"; foreground: root.foreground; focusable: true; onClicked: root.refresh() }
                        }
                    }
                    PanelSeparator { width: parent.width; foreground: root.foreground }
                    Rectangle {
                        width: parent.width
                        implicitHeight: hardwareColumn.implicitHeight + Style.space(24)
                        color: Style.selectedFillFor(root.foreground, Color.accent)
                        radius: Style.cornerRadius
                        Column {
                            id: hardwareColumn
                            x: Style.space(12); y: Style.space(12)
                            width: parent.width - Style.space(24)
                            spacing: Style.space(8)
                            Label {
                                text: root.device ? root.device.device.split(" at ")[0] : "USB audio hardware"
                                font.bold: true
                                elide: Text.ElideRight
                                wrapMode: Text.NoWrap
                            }
                            Row {
                                width: parent.width
                                spacing: Style.space(16)
                                Column {
                                    width: (parent.width - Style.space(32)) / 3
                                    Label { text: root.activeRate; color: Color.accent; font.pixelSize: Style.font.title }
                                    Label { text: "LIVE RATE"; font.pixelSize: Style.font.caption; color: root.dim }
                                }
                                Column {
                                    width: (parent.width - Style.space(32)) / 3
                                    Label { text: root.info.graph.length ? root.info.graph.map(function(g) { return String(g.quantum) }).filter(function(q, i, a) { return a.indexOf(q) === i }).join(" / ") : "—"; font.pixelSize: Style.font.title }
                                    Label { text: "SAMPLES"; font.pixelSize: Style.font.caption; color: root.dim }
                                }
                                Column {
                                    width: (parent.width - Style.space(32)) / 3
                                    Label { text: root.validBits; font.pixelSize: Style.font.title }
                                    Label { text: "HARDWARE"; font.pixelSize: Style.font.caption; color: root.dim }
                                }
                            }
                        }
                    }
                    Column {
                        width: parent.width; spacing: Style.space(6)
                        Label { text: "Temporary audio settings"; font.bold: true }
                        Label { text: "Sample rate"; font.bold: true }
                        Flow {
                            width: parent.width; spacing: Style.space(4)
                            Repeater {
                                model: [0, 44100, 48000, 88200, 96000]
                                Button {
                                    required property int modelData
                                    text: modelData ? (modelData / 1000) + "k" : "Auto"
                                    selected: root.chosenRate === modelData
                                    focusable: true
                                    enabled: !root.busy && !root.pending
                                    foreground: root.foreground
                                    onClicked: root.chosenRate = modelData
                                }
                            }
                        }
                        Label { text: "Block size (samples)"; font.bold: true }
                        Flow {
                            width: parent.width; spacing: Style.space(4)
                            Repeater {
                                model: [0, 64, 128, 256, 512, 1024, 2048]
                                Button {
                                    required property int modelData
                                    text: modelData ? String(modelData) : "Auto"
                                    selected: root.chosenBuffer === modelData
                                    focusable: true
                                    enabled: !root.busy && !root.pending
                                    foreground: root.foreground
                                    onClicked: root.chosenBuffer = modelData
                                }
                            }
                        }
                        Label {
                            text: "Current overrides: " + (root.settingValue(root.info.settings["clock.force-rate"]) ? root.settingValue(root.info.settings["clock.force-rate"]) / 1000 + "k" : "auto rate") + " / " + (root.settingValue(root.info.settings["clock.force-quantum"]) ? root.settingValue(root.info.settings["clock.force-quantum"]) : "auto buffer")
                            color: root.dim; font.pixelSize: Style.font.bodySmall
                        }
                        Row {
                            spacing: Style.space(8)
                            visible: !root.pending
                            Button { text: root.busy && root.actionKind === "apply" ? "Working…" : "Apply now"; iconText: "󰄬"; selected: true; focusable: true; enabled: !root.busy; foreground: root.foreground; onClicked: root.request("apply") }
                            Button { text: "Reset to auto"; focusable: true; enabled: !root.busy; foreground: root.foreground; onClicked: root.request("auto") }
                        }
                    }
                    PanelSeparator { width: parent.width; foreground: root.foreground }
                    Column {
                        width: parent.width; spacing: Style.space(6)
                        Label { text: "Default audio settings"; font.bold: true }
                        Label {
                            text: root.defaultsDirty ? "Unsaved changes" : root.hasSavedDefaults ? "Saved: " + root.pairText(root.savedValue("rate"), root.savedValue("quantum")) : "Not saved"
                            color: root.dim; font.pixelSize: Style.font.bodySmall
                        }
                        Label { text: "Default sample rate"; font.bold: true }
                        Flow {
                            width: parent.width; spacing: Style.space(4)
                            Repeater {
                                model: [0, 44100, 48000, 88200, 96000]
                                Button {
                                    required property int modelData
                                    text: modelData ? (modelData / 1000) + "k" : "Auto"
                                    selected: root.defaultRate === modelData
                                    focusable: true
                                    enabled: !root.busy && !root.pending
                                    foreground: root.foreground
                                    onClicked: { root.defaultRate = modelData; root.defaultsDirty = true }
                                }
                            }
                        }
                        Label { text: "Default block size (samples)"; font.bold: true }
                        Flow {
                            width: parent.width; spacing: Style.space(4)
                            Repeater {
                                model: [0, 64, 128, 256, 512, 1024, 2048]
                                Button {
                                    required property int modelData
                                    text: modelData ? String(modelData) : "Auto"
                                    selected: root.defaultBuffer === modelData
                                    focusable: true
                                    enabled: !root.busy && !root.pending
                                    foreground: root.foreground
                                    onClicked: { root.defaultBuffer = modelData; root.defaultsDirty = true }
                                }
                            }
                        }
                        Row {
                            spacing: Style.space(8); visible: !root.pending
                            Button { text: root.busy && root.actionKind === "save" ? "Working…" : "Save defaults"; iconText: "󰆓"; focusable: true; enabled: !root.busy; foreground: root.foreground; onClicked: root.request("save") }
                            Button { text: "Clear defaults"; focusable: true; enabled: !root.busy; foreground: root.foreground; onClicked: root.request("remove") }
                        }
                    }
                    Rectangle {
                        width: parent.width
                        visible: root.pending !== ""
                        implicitHeight: confirmColumn.implicitHeight + Style.space(24)
                        color: Style.selectedFillFor(root.foreground, Color.accent)
                        radius: Style.cornerRadius
                        Column {
                            id: confirmColumn
                            x: Style.space(12); y: Style.space(12)
                            width: parent.width - Style.space(24); spacing: Style.space(10)
                            Label {
                                text: root.pending === "apply" || root.pending === "auto" ? "Stop recording first. This will interrupt system audio." : root.pending === "save" ? "Save these defaults? Current audio will not change." : "Clear saved defaults? Current audio will not change."
                                font.bold: true
                            }
                            Label {
                                text: root.pending === "remove" ? "Saved defaults will be cleared" : root.pairText(root.pendingRate, root.pendingBuffer)
                                color: root.dim
                            }
                            Row {
                                spacing: Style.space(8)
                                Button { text: "Confirm"; selected: true; focusable: true; foreground: root.foreground; onClicked: root.execute() }
                                Button { text: "Cancel"; focusable: true; foreground: root.foreground; onClicked: root.pending = "" }
                            }
                        }
                    }
                    Label { visible: root.message !== ""; text: root.message; color: root.failed ? Color.urgent : Color.accent; font.pixelSize: Style.font.bodySmall }
                }
            }
        }
    }
    component Label: Text {
        width: parent.width
        textFormat: Text.PlainText
        color: root.foreground
        font.family: root.fontFamily
        font.pixelSize: Style.font.body
        wrapMode: Text.WordWrap
    }
}
