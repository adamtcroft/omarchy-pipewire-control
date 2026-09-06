import QtQuick

// Five equalizer strokes, sized like Omarchy's other monochrome bar icons.
Item {
    id: root
    property color color: "white"
    property real size: 16
    implicitWidth: size
    implicitHeight: size
    Row {
        anchors.centerIn: parent
        spacing: root.size / 8
        Repeater {
            model: [0.35, 0.7, 1.0, 0.55, 0.3]
            Rectangle {
                required property real modelData
                width: root.size / 10
                height: root.size * modelData
                anchors.verticalCenter: parent.verticalCenter
                radius: width / 2
                color: root.color
            }
        }
    }
}
