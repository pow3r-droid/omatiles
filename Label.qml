import QtQuick
import qs.Commons
// Wrapping body text.
DeskText {
    font.family: Style.font.family
    color: Color.foreground
    font.pixelSize: Style.font.subtitle
    wrapMode: Text.Wrap
    width: parent ? parent.width : implicitWidth
}
