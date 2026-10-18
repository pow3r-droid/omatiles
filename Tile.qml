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
    // This tile's own menu items, as [{t: label, a: name}]; picking one emits action(name).
    // The menu adds move or resize, send to a desk and remove for every tile.
    property var actions: []
    signal action(string name)
    function openMenu(x, y) { var p = mapToItem(desk, x, y); desk.openTileMenu(tile, p.x, p.y); }
    onPlaceChanged: { liveCol = -1; liveRow = -1; liveW = -1; liveH = -1; }
    visible: !!place && place.enabled && (place.page || 1) === desk.page
    x: desk.cellX(col); y: desk.cellY(row)
    width: desk.spanWidth(spanW); height: desk.spanHeight(spanH)
    // A tile added to a full desk sits on top until it's dragged into place.
    z: drag.pressed || resize.pressed ? 10 : stacked ? 5 : 1
    radius: Style.cornerRadius
    readonly property bool stacked: !!place && place.top === true
    // Stacked: solid, so the tiles underneath don't show through it.
    color: stacked ? Color.background : Util.alpha(Color.background, 0.82)
    border.width: desk.editing || focused ? 2 : 1
    border.color: desk.editing || focused ? desk.ink : Util.alpha(Color.foreground, 0.1)
    clip: true
    Component.onCompleted: desk.registerTile(tile)
    Component.onDestruction: desk.unregisterTile(tile)
    function save() { desk.place(key, {col: col, row: row, w: spanW, h: spanH}); }
    // Right-click, or press and hold, opens the tile's own menu (the launcher's long-press).
    MouseArea {
        anchors.fill: parent; z: -1
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        pressAndHoldInterval: 500
        onPressAndHold: function(m) { tile.openMenu(m.x, m.y); }
        onClicked: function(m) { if (m.button === Qt.RightButton) tile.openMenu(m.x, m.y); else desk.dismiss(); }
    }
    Item {
        id: body
        anchors.fill: parent
        anchors.margins: tile.padded ? Style.spacing.panelPadding - 2 : 0
        opacity: desk.editing && !tile.stacked ? 0.5 : 1
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
            if (m.button === Qt.RightButton) { tile.openMenu(m.x, m.y); return; }
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
        Accessible.role: Accessible.Button
        color: Util.alpha(tone, hot ? 0.45 : 0.2)
        border.width: 1; border.color: tone
        Text { id: label; anchors.centerIn: parent; text: handle.glyph; color: handle.tone; font.family: Style.font.family; font.pixelSize: Style.font.body }
    }
    Handle {
        glyph: "󰑝"; hot: resize.pressed; Accessible.name: "resize"
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
    // Send to another desk page (workspace), where it takes the first free spot:
    // one button per other desk, so any tile reaches any desk in one click.
    Row {
        visible: desk.editing && desk.pages > 1
        spacing: Style.spacing.xs
        anchors { right: closeHandle.left; top: parent.top; topMargin: Style.spacing.sm; rightMargin: Style.spacing.sm }
        Repeater {
            model: { var o = []; for (var n = 1; n <= desk.pages; n++) if (n !== desk.page) o.push(n); return o; }
            Handle {
                required property int modelData
                glyph: "\uf061 " + modelData; hot: sendMouse.containsMouse; Accessible.name: "send to desk " + modelData
                MouseArea { id: sendMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: desk.move(tile.key, parent.modelData) }
            }
        }
    }
    // Remove: hides a built-in tile, or puts a widget in the trash (the desk offers undo).
    Handle {
        id: closeHandle
        glyph: ""; tone: desk.danger; hot: closeMouse.containsMouse; Accessible.name: "remove"
        anchors { right: parent.right; top: parent.top; margins: Style.spacing.sm }
        MouseArea { id: closeMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: desk.remove(tile.key) }
    }
}
