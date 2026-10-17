import QtQuick
import qs.Commons
import Quickshell
import Quickshell.Io
import "Ui.js" as Ui
// One agent's conversation in a desk tile: its transcript (chat/<agent>/log.json,
// written by the backend, so it survives restarts), a line to type into, a new
// chat, and the full CLI in a terminal.
Item {
    id: chat
    anchors.fill: parent
    property string agent
    property string name
    property string where: ""
    // false when the agent's CLI is known to be missing on the machine it runs on.
    property bool available: true
    property bool busy: false
    property double now: Date.now()
    property double sentAt: 0
    property var desk
    property color ink: Color.accent
    property color muted: Color.muted
    property var log: []
    readonly property var last: log.length ? log[log.length - 1] : null
    signal send(string text)
    signal retry()
    signal fresh()
    signal terminal()
    signal link(string url)
    onBusyChanged: if (busy) sentAt = Date.now()
    function focusInput() { if (chat.desk) chat.desk.typing = true; line.forceActiveFocus(); }

    // The desk bumps this when a turn starts or ends, or a new chat clears the log.
    property int epoch: 0
    onEpochChanged: logFile.reload()
    FileView {
        id: logFile
        path: Quickshell.env("HOME") + "/.cache/omatiles/chat/" + chat.agent + "/log.json"
        watchChanges: true; printErrors: false
        onFileChanged: reload()
        onLoaded: { try { var l = JSON.parse(text()); chat.log = Array.isArray(l) ? l : []; } catch(e) { chat.log = []; } }
        onLoadFailed: chat.log = []
    }

    component Link: Text {
        id: link
        property bool on: true
        signal hit()
        font.family: Style.font.family; font.pixelSize: Style.font.body
        color: !on ? Util.alpha(chat.muted, 0.5) : hover.containsMouse ? Color.foreground : chat.ink
        MouseArea { id: hover; anchors.fill: parent; anchors.margins: -6; hoverEnabled: true; enabled: link.on; cursorShape: Qt.PointingHandCursor; onClicked: link.hit() }
    }

    Item {
        id: head; width: parent.width; height: 22
        Row {
            spacing: Style.spacing.lg; anchors.verticalCenter: parent.verticalCenter
            Text { id: chatName; text: chat.name; color: chat.ink; font.family: Style.font.family; font.pixelSize: Style.font.heading }
            Text { y: chatName.baselineOffset - baselineOffset; text: "on " + chat.where; color: chat.muted; font.family: Style.font.family; font.pixelSize: Style.font.body }
        }
        Row {
            anchors { right: parent.right; verticalCenter: parent.verticalCenter }
            spacing: Style.spacing.huge
            Link { text: "new chat"; on: !chat.busy && chat.log.length > 0; onHit: chat.fresh() }
            Link { text: "terminal"; onHit: chat.terminal() }
        }
    }
    Rectangle { id: rule; y: head.height + Style.spacing.lg; width: parent.width; height: 1; color: Util.alpha(Color.foreground, 0.1) }

    Flickable {
        id: scroll
        anchors { top: rule.bottom; topMargin: Style.spacing.xl; left: parent.left; right: parent.right; bottom: input.top; bottomMargin: Style.spacing.xl }
        contentWidth: width; contentHeight: messages.implicitHeight; clip: true
        boundsBehavior: Flickable.StopAtBounds
        onContentHeightChanged: contentY = Math.max(0, contentHeight - height)
        onHeightChanged: contentY = Math.max(0, contentHeight - height)
        Column {
            id: messages; width: scroll.width; spacing: Style.spacing.xxl
            Text {
                visible: chat.log.length === 0 && !chat.busy; width: parent.width; wrapMode: Text.Wrap
                text: chat.available
                    ? "Ask " + chat.name + " anything. Turns run read-only " + (chat.where === "this machine" ? "here" : "on " + chat.where) + ". The conversation stays until new chat; terminal opens the full CLI on it."
                    : chat.name + " isn't installed here. Install its CLI, or set chat.host in omatiles.json to run it on another machine."
                color: chat.muted; font.family: Style.font.family; font.pixelSize: Style.font.body
            }
            Repeater {
                model: chat.log
                Column {
                    id: entry
                    required property var modelData
                    required property int index
                    readonly property bool mine: modelData.who === "you"
                    readonly property bool lastError: !!modelData.error && index === chat.log.length - 1
                    width: messages.width; spacing: Style.spacing.xs
                    Text {
                        width: parent.width; wrapMode: Text.Wrap
                        leftPadding: entry.mine ? 0 : Style.spacing.xxl
                        text: entry.mine ? "› " + entry.modelData.text : entry.modelData.text
                        textFormat: entry.mine || entry.modelData.error ? Text.PlainText : Text.MarkdownText
                        color: entry.mine ? chat.ink : entry.modelData.error ? Color.urgent : Color.foreground
                        font.family: Style.font.family; font.pixelSize: Style.font.subtitle; lineHeight: 1.15
                        onLinkActivated: function(url) { chat.link(url); }
                        MouseArea { anchors.fill: parent; acceptedButtons: Qt.NoButton; cursorShape: parent.hoveredLink ? Qt.PointingHandCursor : Qt.ArrowCursor }
                    }
                    // What the CLI actually said, for when the sentence above is not enough.
                    Text {
                        visible: entry.lastError && !!entry.modelData.detail
                        width: parent.width; leftPadding: Style.spacing.xxl; wrapMode: Text.WrapAnywhere; maximumLineCount: 3; elide: Text.ElideRight
                        text: entry.modelData.detail || ""; color: chat.muted; font.family: Style.font.family; font.pixelSize: Style.font.body
                    }
                    Row {
                        visible: entry.lastError && !chat.busy; leftPadding: Style.spacing.xxl; spacing: Style.spacing.huge; topPadding: Style.spacing.xs
                        Link { text: " retry"; onHit: chat.retry() }
                        Link { text: "open terminal"; onHit: chat.terminal() }
                    }
                }
            }
            Column {
                // The shell restarted (or the backend died) while a reply was on its way.
                visible: !chat.busy && !!chat.last && chat.last.who === "you"
                width: parent.width; spacing: Style.spacing.xs; leftPadding: Style.spacing.xxl
                Text { width: parent.width - parent.leftPadding; wrapMode: Text.Wrap; text: "No reply came back."; color: chat.muted; font.family: Style.font.family; font.pixelSize: Style.font.body }
                Link { text: " send it again"; onHit: chat.retry() }
            }
            Text {
                visible: chat.busy; leftPadding: Style.spacing.xxl
                text: chat.name + " is thinking · " + Math.max(0, Math.round((chat.now - chat.sentAt) / 1000)) + "s"
                color: chat.muted; font.family: Style.font.family; font.pixelSize: Style.font.body
            }
        }
    }

    Rectangle {
        id: input
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
        height: Style.spacing.controlHeight + 6; radius: Style.cornerRadius
        color: Util.alpha(Color.foreground, 0.06)
        border.width: 1; border.color: line.activeFocus ? Util.alpha(chat.ink, 0.7) : "transparent"
        TextInput {
            id: line
            anchors { fill: parent; leftMargin: Style.spacing.controlPaddingX; rightMargin: 34 }
            verticalAlignment: TextInput.AlignVCenter
            color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.subtitle; clip: true; selectByMouse: true
            selectionColor: Util.alpha(chat.ink, 0.4)
            Text {
                anchors.verticalCenter: parent.verticalCenter
                visible: !line.text; text: chat.busy ? "waiting for " + chat.name + "…" : "message " + chat.name + "…"
                color: chat.muted; font: line.font
            }
            onAccepted: if (!chat.busy && text.trim()) { chat.send(text.trim()); text = ""; }
            // In keyboard mode, Esc hands the keys back to the desk.
            Keys.onEscapePressed: { focus = false; if (chat.desk) { chat.desk.typing = false; if (chat.desk.focusing) chat.desk.forceActiveFocus(); } }
            onActiveFocusChanged: if (!activeFocus && chat.desk) chat.desk.typing = false
        }
        Text {
            anchors { right: parent.right; rightMargin: Style.spacing.xxl; verticalCenter: parent.verticalCenter }
            text: ""; font.family: Style.font.family; font.pixelSize: Style.font.subtitle
            color: line.text.trim() && !chat.busy ? chat.ink : Util.alpha(chat.muted, 0.5)
            MouseArea {
                anchors.fill: parent; anchors.margins: -8; cursorShape: Qt.PointingHandCursor
                onClicked: if (!chat.busy && line.text.trim()) { chat.send(line.text.trim()); line.text = ""; }
            }
        }
        MouseArea {
            anchors { fill: parent; rightMargin: 34 } enabled: !line.activeFocus
            onClicked: chat.focusInput()
        }
    }
}
