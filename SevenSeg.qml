import QtQuick
import qs.Commons
// Seven-segment readout for digits and ':' with the unlit "8" segments
// ghosted behind, like an LCD clock.
Row {
    id: seg
    property string text: ""
    property real digitHeight: 64
    property color color: Color.accent
    readonly property real thick: Math.max(3, digitHeight * 0.12)
    readonly property real digitWidth: digitHeight * 0.55
    // a b c d e f g, top then clockwise, g in the middle.
    readonly property var map: ({"0":"abcdef","1":"bc","2":"abged","3":"abgcd","4":"fgbc","5":"afgcd",
                                 "6":"afgedc","7":"abc","8":"abcdefg","9":"abcfgd"})
    spacing: digitHeight * 0.1
    Repeater {
        model: seg.text.split("")
        Item {
            required property string modelData
            readonly property bool colon: modelData === ":"
            readonly property string lit: seg.map[modelData] || ""
            width: colon ? seg.thick * 1.6 : seg.digitWidth
            height: seg.digitHeight
            // Colon dots.
            Repeater {
                model: parent.colon ? [0.3, 0.7] : []
                Rectangle {
                    required property real modelData
                    width: seg.thick; height: seg.thick; radius: 1
                    x: (parent.width - width) / 2; y: seg.digitHeight * modelData - height / 2
                    color: seg.color
                }
            }
            Repeater {
                model: parent.colon ? [] : [
                    {k:"a", x:seg.thick*0.6, y:0, w:seg.digitWidth-seg.thick*1.2, h:seg.thick},
                    {k:"b", x:seg.digitWidth-seg.thick, y:seg.thick*0.6, w:seg.thick, h:seg.digitHeight/2-seg.thick*0.9},
                    {k:"c", x:seg.digitWidth-seg.thick, y:seg.digitHeight/2+seg.thick*0.3, w:seg.thick, h:seg.digitHeight/2-seg.thick*0.9},
                    {k:"d", x:seg.thick*0.6, y:seg.digitHeight-seg.thick, w:seg.digitWidth-seg.thick*1.2, h:seg.thick},
                    {k:"e", x:0, y:seg.digitHeight/2+seg.thick*0.3, w:seg.thick, h:seg.digitHeight/2-seg.thick*0.9},
                    {k:"f", x:0, y:seg.thick*0.6, w:seg.thick, h:seg.digitHeight/2-seg.thick*0.9},
                    {k:"g", x:seg.thick*0.6, y:(seg.digitHeight-seg.thick)/2, w:seg.digitWidth-seg.thick*1.2, h:seg.thick}]
                Rectangle {
                    required property var modelData
                    x: modelData.x; y: modelData.y; width: modelData.w; height: modelData.h; radius: 1
                    color: parent.lit.indexOf(modelData.k) !== -1 ? seg.color : Util.alpha(seg.color, 0.07)
                }
            }
        }
    }
}
