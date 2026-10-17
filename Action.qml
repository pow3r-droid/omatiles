import QtQuick
import qs.Commons
import "Ui.js" as Ui
// A button in the desk's accent: outlined, filled on hover, dimmed while disabled.
Rectangle {
    id: action
    property string text
    signal clicked()
    readonly property color ink: Ui.ink(Color)
    width: parent ? parent.width : 80
    height: Style.spacing.controlHeight
    radius: Style.cornerRadius
    opacity: enabled ? 1 : 0.45
    color: mouse.containsMouse ? Util.alpha(ink, 0.22) : Util.alpha(ink, 0.08)
    border.width: 1; border.color: Util.alpha(ink, mouse.containsMouse ? 0.7 : 0.4)
    implicitWidth: label.implicitWidth + 2 * Style.spacing.xxl
    Text { id: label; anchors.centerIn: parent; text: action.text; color: action.ink; font.family: Style.font.family; font.pixelSize: Style.font.body }
    MouseArea { id: mouse; anchors.fill: parent; hoverEnabled: true; cursorShape: action.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor; onClicked: action.clicked() }
}
