import QtQuick
import qs.Commons
// A machine in fastfetch style: facts on the left, services and containers on
// the right. The local and remote machine cards both use it with their probe.
Row {
    id: info
    property var machine: null
    property string user: ""
    // [{t: label, state: "running" | "2/3 running" | "stopped" ..., ok: bool}]
    property var services: []
    property bool live: false
    property string status: ""
    property string waiting: ""
    property string button: ""
    property color ink: Color.accent
    property color muted: Color.muted
    signal clicked()
    // On-demand cards show a refresh link beside their status.
    property bool refreshable: false
    signal refresh()
    function logo(os) {
        var o = (os || "").toLowerCase();
        return o.indexOf("arch") !== -1 || o.indexOf("omarchy") !== -1 ? "" : o.indexOf("debian") !== -1 ? ""
             : o.indexOf("ubuntu") !== -1 ? "" : o.indexOf("fedora") !== -1 ? "" : o.indexOf("nixos") !== -1 ? "" : "";
    }
    readonly property var facts: !machine ? [] : [
        ["os", machine.os || "—"], ["host", machine.host || "—"], ["kernel", machine.kernel || "—"],
        ["uptime", machine.uptime || "—"], ["packages", Number(machine.packages) > 0 ? machine.packages + " (pacman)" : "—"],
        ["shell", machine.shell || "—"], ["cpu", (machine.cpuName||"—").replace(/ with .*/,"") + (machine.cpu!==undefined && machine.cpu!==null ? " · " + Math.round(machine.cpu) + "%" : "")],
        ["memory", machine.memTotal && machine.mem !== null ? (machine.mem*machine.memTotal/100/1073741824).toFixed(1) + "G / " + Math.round(machine.memTotal/1073741824) + "G (" + Math.round(machine.mem) + "%)" : "—"],
        ["disk", machine.diskSize ? Math.round(machine.disk*machine.diskSize/100/1e9) + "G / " + Math.round(machine.diskSize/1e9) + "G (" + Math.round(machine.disk) + "%)" : "—"],
        ["temp", machine.temp!==null && machine.temp!==undefined ? machine.temp + "°C" : "—"]]
    anchors.fill: parent; spacing: Style.spacing.huge
    Column {
        width: info.width*0.6; spacing: Style.spacing.xs
        Row {
            spacing: Style.spacing.xl; bottomPadding: Style.spacing.md
            Text { text: info.logo(info.machine ? info.machine.os : ""); color: info.ink; font.family: Style.font.family; font.pixelSize: 34 }
            Column {
                spacing: Style.spacing.sm
                Text { text: info.user; color: info.ink; font.family: Style.font.family; font.pixelSize: Style.font.heading }
                Row {
                    spacing: Style.spacing.xs
                    Repeater {
                        model: [Color.urgent, info.ink, Util.alpha(info.ink,0.6), Color.foreground, info.muted]
                        Rectangle { required property color modelData; width: 14; height: 5; color: modelData }
                    }
                }
            }
        }
        Repeater {
            model: info.facts
            Row {
                required property var modelData
                width: parent.width; spacing: Style.spacing.lg
                Text { width: 72; text: modelData[0]; color: info.ink; font.family: Style.font.family; font.pixelSize: Style.font.body }
                Text { width: parent.width-80; text: modelData[1]; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body; elide: Text.ElideRight }
            }
        }
        Text { visible: !info.machine; width: parent.width; wrapMode: Text.Wrap; text: info.waiting; color: info.muted; font.family: Style.font.family; font.pixelSize: Style.font.body }
    }
    Column {
        width: info.width*0.4-info.spacing; spacing: Style.spacing.md
        Text { visible: info.services.length > 0; text: "services"; color: info.muted; font.family: Style.font.family; font.pixelSize: Style.font.body }
        Repeater {
            model: info.services
            Row {
                required property var modelData
                width: parent.width; spacing: Style.spacing.md
                Rectangle { width: 7; height: 7; y: 5; radius: 4; color: modelData.ok ? info.ink : Color.urgent }
                // The state is spelled out too, so it never rests on color alone.
                Text {
                    width: parent.width - 14; elide: Text.ElideRight
                    text: modelData.t + (modelData.state ? "  " : ""); color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body
                    Text { x: parent.implicitWidth; visible: parent.implicitWidth < parent.width; text: modelData.state || ""; color: modelData.ok ? info.muted : Color.urgent; font: parent.font }
                }
            }
        }
        Text { visible: conts.count > 0; text: "containers"; color: info.muted; font.family: Style.font.family; font.pixelSize: Style.font.body; topPadding: Style.spacing.sm }
        Grid {
            width: parent.width; columns: 2; rowSpacing: Style.spacing.xs; columnSpacing: Style.spacing.lg
            Repeater {
                id: conts
                model: info.machine && info.machine.containers ? info.machine.containers : []
                Row {
                    required property var modelData
                    width: (parent.width-Style.spacing.lg)/2; spacing: 5
                    Rectangle { width: 5; height: 5; y: 6; radius: 3; color: modelData.up ? info.ink : Color.urgent }
                    Text { width: parent.width-10; elide: Text.ElideRight; text: modelData.name + (modelData.up ? "" : " · down"); color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body }
                }
            }
        }
        Text {
            visible: !!info.machine && !!info.machine.failed && info.machine.failed.length>0
            width: parent.width; wrapMode: Text.Wrap; font.family: Style.font.family; font.pixelSize: Style.font.body; color: Color.urgent
            text: info.machine && info.machine.failed ? "failed: " + info.machine.failed.join(", ") : ""
        }
        Flow {
            width: parent.width; spacing: Style.spacing.xl; topPadding: Style.spacing.sm
            Text {
                visible: info.status !== ""
                width: Math.min(implicitWidth, parent.width); wrapMode: Text.Wrap
                font.family: Style.font.family; font.pixelSize: Style.font.body
                color: info.live ? info.muted : Color.urgent
                text: info.status
            }
            Text {
                visible: info.refreshable
                text: " refresh"; font.family: Style.font.family; font.pixelSize: Style.font.body
                color: refreshMouse.containsMouse ? Color.foreground : info.ink
                MouseArea { id: refreshMouse; anchors.fill: parent; anchors.margins: -6; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: info.refresh() }
            }
        }
        Action { visible: info.button !== ""; width: Math.min(parent.width, Math.max(150, implicitWidth)); text: info.button; onClicked: info.clicked() }
    }
}
