import QtQuick
import qs.Commons
// One grid tile. Its cell comes from the desk config; while arranging, dragging
// moves it and the corner resizes it, both snapped to grid cells, and the drop
// is saved. Content is clipped to the tile.
Rectangle {
    id: tile
    required property var desk
    property string key
    property var place
    property bool padded: true
    property real liveCol: -1
    property real liveRow: -1
    property real liveW: -1
    property real liveH: -1
    readonly property int col: liveCol >= 0 ? liveCol : place.col
    readonly property int row: liveRow >= 0 ? liveRow : place.row
    readonly property int spanW: liveW >= 0 ? liveW : place.w
    readonly property int spanH: liveH >= 0 ? liveH : place.h
    readonly property bool focused: desk.focusKey === key && visible
    default property alias content: body.data
    readonly property alias body: body
    // Enter on the focused tile (keyboard mode) runs this.
    signal activated()
    onPlaceChanged: { liveCol = -1; liveRow = -1; liveW = -1; liveH = -1; }
    visible: !!place && place.enabled && (place.page || 1) === desk.page
    x: desk.cellX(col); y: desk.cellY(row)
    width: desk.spanWidth(spanW); height: desk.spanHeight(spanH)
    z: drag.pressed || resize.pressed ? 10 : 1
    radius: Style.cornerRadius
    color: Util.alpha(Color.background, 0.82)
    border.width: desk.editing || focused ? 2 : 1
    border.color: desk.editing || focused ? desk.ink : Util.alpha(Color.foreground, 0.1)
    clip: true
    Component.onCompleted: desk.registerTile(tile)
    Component.onDestruction: desk.unregisterTile(tile)
    function save() { desk.place(key, {col: col, row: row, w: spanW, h: spanH}); }
    MouseArea {
        anchors.fill: parent; z: -1
        acceptedButtons: Qt.RightButton
        onClicked: function(m) { var p = mapToItem(desk, m.x, m.y); desk.openMenu(p.x, p.y); }
    }
    Item {
        id: body
        anchors.fill: parent
        anchors.margins: tile.padded ? Style.spacing.panelPadding - 2 : 0
        opacity: desk.editing ? 0.5 : 1
    }
    MouseArea {
        id: drag
        anchors.fill: parent
        visible: desk.editing
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
        property real offX
        property real offY
        onPressed: function(m) {
            if (m.button === Qt.RightButton) { var q = mapToItem(desk, m.x, m.y); desk.openMenu(q.x, q.y); return; }
            offX = m.x; offY = m.y;
        }
        onPositionChanged: function(m) {
            if (!pressed) return;
            var p = mapToItem(tile.parent, m.x, m.y);
            tile.liveCol = desk.colAt(p.x - offX, tile.spanW);
            tile.liveRow = desk.rowAt(p.y - offY, tile.spanH);
        }
        onReleased: function(m) { if (m.button === Qt.LeftButton) tile.save(); }
    }
    component Handle: Rectangle {
        id: handle
        property string glyph
        property color tone: tile.desk.ink
        property bool hot: false
        visible: tile.desk.editing
        height: 24; width: Math.max(24, label.implicitWidth + 12); radius: Style.cornerRadius
        color: Util.alpha(tone, hot ? 0.45 : 0.2)
        border.width: 1; border.color: tone
        Text { id: label; anchors.centerIn: parent; text: handle.glyph; color: handle.tone; font.family: Style.font.family; font.pixelSize: Style.font.body }
    }
    Handle {
        glyph: "󰑝"; hot: resize.pressed
        anchors { right: parent.right; bottom: parent.bottom; margins: Style.spacing.sm }
        MouseArea {
            id: resize
            anchors.fill: parent
            cursorShape: Qt.SizeFDiagCursor
            onPositionChanged: function(m) {
                if (!pressed) return;
                var p = mapToItem(tile.parent, m.x, m.y);
                tile.liveW = desk.spanAt(p.x - tile.x, tile.col, true);
                tile.liveH = desk.spanAt(p.y - tile.y, tile.row, false);
            }
            onReleased: tile.save()
        }
    }
    // Send to the next desk page (workspace), where it takes the first free spot.
    Handle {
        glyph: " " + (desk.page % desk.pages + 1); hot: moveMouse.containsMouse
        anchors { right: closeHandle.left; top: parent.top; topMargin: Style.spacing.sm; rightMargin: Style.spacing.sm }
        MouseArea { id: moveMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: desk.move(tile.key, desk.page % desk.pages + 1) }
    }
    // Remove: hides a built-in tile, or puts a widget in the trash (the desk offers undo).
    Handle {
        id: closeHandle
        glyph: ""; tone: Color.urgent; hot: closeMouse.containsMouse
        anchors { right: parent.right; top: parent.top; margins: Style.spacing.sm }
        MouseArea { id: closeMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: desk.remove(tile.key) }
    }
}
