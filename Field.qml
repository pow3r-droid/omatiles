import QtQuick
import qs.Commons
import "Ui.js" as Ui
// A one-line text field; clicking it lets the desk take the keyboard.
Rectangle {
    id: field
    property alias text: input.text
    property alias input: input
    property string placeholder
    property var desk
    signal accepted()
    readonly property color ink: Ui.ink(Color)
    function focusIn() { if(desk) desk.typing=true; input.forceActiveFocus(); }
    width: parent ? parent.width : 200; height: Style.spacing.controlHeight + 4; radius: Style.cornerRadius
    color: Util.alpha(Color.foreground, 0.06)
    border.width: 1; border.color: input.activeFocus ? Util.alpha(ink, 0.7) : "transparent"
    TextInput {
        id: input; anchors.fill: parent; anchors.leftMargin: Style.spacing.controlPaddingX; anchors.rightMargin: Style.spacing.controlPaddingX
        verticalAlignment: TextInput.AlignVCenter
        color: Color.foreground; clip: true; selectByMouse: true; selectionColor: Util.alpha(field.ink, 0.4)
        font.family: Style.font.family; font.pixelSize: Style.font.body
        Text { anchors.verticalCenter: parent.verticalCenter; visible: !input.text; text: field.placeholder; color: Ui.muted(Color); font: input.font }
        onAccepted: field.accepted()
        Keys.onEscapePressed: { focus=false; if(field.desk) field.desk.typing=false; }
    }
    MouseArea { anchors.fill: parent; enabled: !input.activeFocus; cursorShape: Qt.IBeamCursor; onClicked: field.focusIn() }
}
