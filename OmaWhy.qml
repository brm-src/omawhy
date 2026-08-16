import Quickshell
import Quickshell.Io
import QtQuick
import qs.Commons
import qs.Ui

Item {
  id: root

  readonly property string pluginId: "io.github.brm-src.omawhy"
  readonly property string helperPath: Qt.resolvedUrl("omawhy.py").toString().replace("file://", "")
  property bool opened: false
  property string phase: "home" // home, pick, inspect, confirm, shortcut, status
  property var selected: ({})
  property var explanation: ({})
  property var diagnostic: ({})
  property string status: ""
  property var processCallback: null

  function open() {
    root.opened = true
    root.phase = "home"
    root.selected = ({})
    root.explanation = ({})
    root.diagnostic = ({})
    root.status = "¿Qué quieres entender?"
  }

  function close() {
    root.opened = false
    root.phase = "home"
    root.selected = ({})
    root.explanation = ({})
    root.diagnostic = ({})
    root.status = ""
  }

  function toggle() {
    if (root.opened) root.close()
    else root.open()
  }

  function runHelper(args, callback) {
    if (helper.running) return
    root.processCallback = callback
    helper.command = ["python3", root.helperPath].concat(args)
    helper.running = true
  }

  function handlePayload(raw) {
    var payload
    try {
      payload = JSON.parse(String(raw || "{}"))
    } catch (error) {
      root.status = "OmaWhy no pudo leer la respuesta del sistema."
      return
    }
    if (root.processCallback) root.processCallback(payload)
    root.processCallback = null
  }

  function loadExplanation() {
    root.status = "Buscando reglas que coincidan…"
    root.runHelper(["explain", "--window-json", JSON.stringify(root.selected)], function(payload) {
      if (!payload.ok) {
        root.status = payload.error || "No se pudieron analizar las reglas."
        return
      }
      root.explanation = payload.explanation || ({})
      root.status = root.explanation.message || "Análisis listo."
    })
  }

  function effectText(match) {
    var effects = match.effects || ({})
    var items = []
    if (effects.workspace) items.push("workspace " + effects.workspace)
    if (effects.monitor) items.push("monitor " + effects.monitor)
    if (effects.float !== undefined) items.push("flotante " + (effects.float ? "sí" : "no"))
    if (effects.fullscreen !== undefined) items.push("fullscreen " + (effects.fullscreen ? "sí" : "no"))
    if (effects.pin !== undefined) items.push("fijada " + (effects.pin ? "sí" : "no"))
    if (effects.opacity) items.push("opacidad " + effects.opacity)
    if (effects.tag) items.push("tag " + effects.tag)
    return items.length ? items.join(" · ") : "regla coincidente"
  }

  function openMatchedRule(match) {
    root.runHelper(["open-rule", "--path", String(match.path || "")], function(payload) {
      root.status = payload.message || payload.error || "Listo."
    })
  }

  function openShortcutSource() {
    var events = root.diagnostic.events || []
    var source = root.diagnostic.binding || (events.length ? events[events.length - 1] : ({}))
    if (source.path) root.openMatchedRule(source)
  }

  function startWindowQuestion() {
    root.phase = "pick"
    root.status = "Haz clic sobre la ventana que quedó rara. Esc cancela."
  }

  function inspectShortcut() {
    var keys = shortcutInput.text.trim()
    if (!keys) {
      root.status = "Escribe un atajo, por ejemplo: Super Shift I."
      return
    }
    root.status = "Buscando ese atajo…"
    root.runHelper(["shortcut", "--keys", keys], function(payload) {
      if (!payload.ok) {
        root.status = payload.error || "No se pudo revisar el atajo."
        return
      }
      root.diagnostic = payload.diagnosis || ({})
      root.status = root.diagnostic.message || "Atajo revisado."
    })
  }

  function inspectDesktop() {
    root.status = "Revisando Hyprland, Quickshell y el atajo…"
    root.runHelper(["desktop-status"], function(payload) {
      if (!payload.ok) {
        root.status = payload.error || "No se pudo revisar el escritorio."
        return
      }
      root.diagnostic = payload.status || ({})
      root.status = root.diagnostic.message || "Estado revisado."
    })
  }

  function inspectAtCursor() {
    root.status = "Leyendo la ventana…"
    root.runHelper(["inspect-at-cursor"], function(payload) {
      if (!payload.ok) {
        root.status = payload.error || "No se encontró una ventana."
        return
      }
      root.selected = payload.window
      root.phase = "inspect"
      root.status = "Ventana inspeccionada."
      Qt.callLater(root.loadExplanation)
    })
  }

  function action(name) {
    if (name === "remember") {
      root.phase = "confirm"
      root.status = "Revisa la regla antes de guardarla."
      return
    }
    if (name === "undo" || name === "open-rules") {
      root.runHelper([name], function(payload) { root.status = payload.message || payload.error || "Listo." })
      return
    }
    root.runHelper(["action", name, "--window-json", JSON.stringify(root.selected)], function(payload) {
      root.status = payload.message || payload.error || "Listo."
    })
  }

  function saveRememberedRule() {
    root.runHelper(["remember", "--window-json", JSON.stringify(root.selected)], function(payload) {
      root.phase = "inspect"
      root.status = payload.message || payload.error || "Listo."
    })
  }

  IpcHandler {
    target: root.pluginId
    function open(): string { root.open(); return "ok" }
    function close(): string { root.close(); return "ok" }
    function show(): string { root.open(); return "ok" }
    function hide(): string { root.close(); return "ok" }
    function toggle(): string { root.toggle(); return "ok" }
  }

  Process {
    id: helper
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.handlePayload(text)
    }
  }

  Variants {
    model: Quickshell.screens

    PanelWindow {
      id: panel
      required property var modelData
      screen: modelData
      visible: root.opened
      anchors { top: true; bottom: true; left: true; right: true }
      color: "transparent"
      exclusionMode: ExclusionMode.Ignore
      WlrLayershell.namespace: root.pluginId
      WlrLayershell.layer: WlrLayer.Overlay
      WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive

      Keys.onEscapePressed: root.close()
      focus: true

      Rectangle {
        anchors.fill: parent
        color: root.phase === "pick" ? Util.alpha(Color.background, 0.18) : Util.alpha(Color.background, 0.66)
      }

      MouseArea {
        anchors.fill: parent
        enabled: root.phase === "pick"
        cursorShape: Qt.CrossCursor
        onClicked: root.inspectAtCursor()
      }

      Rectangle {
        id: pickHint
        visible: root.phase === "pick"
        z: 2
        width: 390
        height: hintText.implicitHeight + 32
        anchors.centerIn: parent
        radius: 12
        color: Util.alpha(Color.background, 0.96)
        border.width: 1
        border.color: Util.alpha(Color.accent, 0.88)

        Text {
          id: hintText
          anchors.fill: parent
          anchors.margins: 16
          text: "OMAWHY\nHaz clic sobre una ventana para entender por qué está ahí.\n\nEsc para cancelar"
          color: Color.foreground
          font.family: Style.font.family
          font.pixelSize: 14
          lineHeight: 1.25
          wrapMode: Text.Wrap
          textFormat: Text.PlainText
        }
      }

      Rectangle {
        id: homeCard
        visible: root.phase === "home"
        z: 3
        width: Math.min(500, parent.width - 36)
        height: homeContent.implicitHeight + 34
        anchors.centerIn: parent
        radius: 14
        color: Util.alpha(Color.background, 0.98)
        border.width: 1
        border.color: Util.alpha(Color.accent, 0.82)

        Column {
          id: homeContent
          anchors.fill: parent
          anchors.margins: 17
          spacing: 11
          Text {
            text: "OMAWHY"
            color: Color.accent
            font.family: Style.font.family
            font.pixelSize: 12
            font.bold: true
            font.letterSpacing: 1.5
          }
          Text {
            width: parent.width
            text: "¿Qué hizo raro Omarchy?"
            color: Color.foreground
            font.family: Style.font.family
            font.pixelSize: 21
            font.bold: true
          }
          Text {
            width: parent.width
            text: "Elige una pregunta. OmaWhy revisa configuración y procesos reales; no inventa una causa si no hay evidencia."
            color: Util.alpha(Color.foreground, 0.70)
            font.family: Style.font.family
            font.pixelSize: 12
            wrapMode: Text.Wrap
          }
          Repeater {
            model: [
              ["Una ventana quedó mal", "¿Por qué abrió aquí, en este monitor o workspace?", "window"],
              ["Un atajo no funciona", "Busca dónde está definido, reemplazado o desactivado.", "shortcut"],
              ["Revisar estado del escritorio", "Comprueba Hyprland, Quickshell y el atajo de OmaWhy.", "status"]
            ]
            delegate: Rectangle {
              width: homeContent.width
              height: optionContent.implicitHeight + 20
              radius: 9
              color: optionMouse.containsMouse ? Util.alpha(Color.accent, 0.22) : Util.alpha(Color.foreground, 0.07)
              Column {
                id: optionContent
                anchors.fill: parent
                anchors.margins: 10
                spacing: 3
                Text { text: modelData[0]; color: Color.foreground; font.family: Style.font.family; font.pixelSize: 14; font.bold: true }
                Text { width: parent.width; text: modelData[1]; color: Util.alpha(Color.foreground, 0.68); font.family: Style.font.family; font.pixelSize: 11; wrapMode: Text.Wrap }
              }
              MouseArea {
                id: optionMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: {
                  if (modelData[2] === "window") root.startWindowQuestion()
                  else if (modelData[2] === "shortcut") { root.phase = "shortcut"; root.diagnostic = ({}) }
                  else { root.phase = "status"; root.diagnostic = ({}); root.inspectDesktop() }
                }
              }
            }
          }
        }
      }

      Rectangle {
        id: card
        visible: (root.phase === "inspect" || root.phase === "confirm") && (!root.selected.monitor || modelData.name === root.selected.monitor)
        z: 3
        width: Math.min(560, parent.width - 36)
        height: Math.min(content.implicitHeight + 34, parent.height - 36)
        anchors.centerIn: parent
        radius: 14
        color: Util.alpha(Color.background, 0.98)
        border.width: 1
        border.color: Util.alpha(Color.accent, 0.82)

        Flickable {
          anchors.fill: parent
          anchors.margins: 17
          contentWidth: width
          contentHeight: content.implicitHeight
          clip: true

          Column {
            id: content
            width: parent.width
            spacing: 9

            Text {
              width: parent.width
              text: root.phase === "confirm" ? "RECORDAR ESTA POSICIÓN" : "OMAWHY"
              color: Color.accent
              font.family: Style.font.family
              font.pixelSize: 12
              font.bold: true
              font.letterSpacing: 1.5
            }

            Text {
              width: parent.width
              text: String(root.selected.title || "Ventana sin título")
              color: Color.foreground
              font.family: Style.font.family
              font.pixelSize: 20
              font.bold: true
              elide: Text.ElideRight
            }

            Rectangle { width: parent.width; height: 1; color: Util.alpha(Color.foreground, 0.18) }

            Repeater {
              model: [
                [root.selected.identifier_kind === "class" ? "Class" : "App ID", root.selected.identifier],
                ["Título", root.selected.title],
                ["Workspace", root.selected.workspace],
                ["Monitor", root.selected.monitor],
                ["Flotante", root.selected.floating ? "sí" : "no"],
                ["Pantalla completa", root.selected.fullscreen ? "sí" : "no"],
                ["Fijada", root.selected.pinned ? "sí" : "no"],
                ["PID", root.selected.pid],
                ["Dirección", root.selected.address]
              ]
              delegate: Row {
                width: content.width
                spacing: 12
                Text {
                  width: 145
                  text: modelData[0]
                  color: Util.alpha(Color.foreground, 0.58)
                  font.family: Style.font.family
                  font.pixelSize: 12
                }
                Text {
                  width: parent.width - 157
                  text: String(modelData[1] || "—")
                  color: Color.foreground
                  font.family: Style.font.family
                  font.pixelSize: 12
                  elide: Text.ElideRight
                }
              }
            }

            Rectangle {
              visible: root.phase === "inspect" && root.explanation.verdict !== undefined
              width: parent.width
              height: whyColumn.implicitHeight + 22
              radius: 9
              color: root.explanation.verdict === "placement-rule"
                ? Util.alpha(Color.accent, 0.18)
                : Util.alpha(Color.foreground, 0.08)
              border.width: 1
              border.color: root.explanation.verdict === "placement-rule"
                ? Util.alpha(Color.accent, 0.75)
                : Util.alpha(Color.foreground, 0.18)

              Column {
                id: whyColumn
                anchors.fill: parent
                anchors.margins: 11
                spacing: 7
                Text {
                  text: root.explanation.verdict === "placement-rule"
                    ? "ESTO PUEDE EXPLICAR DÓNDE QUEDÓ"
                    : root.explanation.verdict === "style-rule"
                      ? "HAY REGLAS, PERO NO MUEVEN LA VENTANA"
                      : "NO HAY REGLA ESTÁTICA COINCIDENTE"
                  color: root.explanation.verdict === "placement-rule" ? Color.accent : Color.foreground
                  font.family: Style.font.family
                  font.pixelSize: 11
                  font.bold: true
                  font.letterSpacing: 1
                }
                Text {
                  width: parent.width
                  text: root.explanation.message || ""
                  color: Color.foreground
                  font.family: Style.font.family
                  font.pixelSize: 12
                  wrapMode: Text.Wrap
                  textFormat: Text.PlainText
                }
              }
            }

            Repeater {
              visible: root.phase === "inspect"
              model: root.explanation.matches || []
              delegate: Rectangle {
                width: content.width
                height: sourceColumn.implicitHeight + 18
                radius: 8
                color: Util.alpha(Color.foreground, 0.06)
                Column {
                  id: sourceColumn
                  anchors.fill: parent
                  anchors.margins: 9
                  spacing: 4
                  Text {
                    width: parent.width
                    text: String(modelData.path || "").split("/").pop() + ":" + modelData.line + " · " + root.effectText(modelData)
                    color: Color.accent
                    font.family: Style.font.family
                    font.pixelSize: 11
                    elide: Text.ElideRight
                  }
                  Text {
                    width: parent.width
                    text: modelData.rule || ""
                    color: Util.alpha(Color.foreground, 0.70)
                    font.family: Style.font.family
                    font.pixelSize: 10
                    elide: Text.ElideRight
                  }
                  Text {
                    text: "Abrir archivo"
                    color: Color.foreground
                    font.family: Style.font.family
                    font.pixelSize: 11
                    font.underline: sourceMouse.containsMouse
                    MouseArea {
                      id: sourceMouse
                      anchors.fill: parent
                      hoverEnabled: true
                      cursorShape: Qt.PointingHandCursor
                      onClicked: root.openMatchedRule(modelData)
                    }
                  }
                }
              }
            }

            Text {
              visible: root.phase === "confirm"
              width: parent.width
              text: "Se escribirá una regla limitada a esta aplicación en la configuración activa de Hyprland. OmaWhy crea un backup y puedes deshacer el último cambio."
              wrapMode: Text.Wrap
              textFormat: Text.PlainText
              color: Util.alpha(Color.foreground, 0.72)
              font.family: Style.font.family
              font.pixelSize: 12
              lineHeight: 1.2
            }

            Flow {
              visible: root.phase === "inspect"
              width: parent.width
              spacing: 7
              Repeater {
                model: [
                  ["Copiar App ID", "copy-app-id"], ["Copiar Class", "copy-class"], ["Copiar título", "copy-title"],
                  ["Copiar regla", "copy-rule"], ["Mover aquí", "move-current"], ["Centrar", "center"],
                  ["Alternar flotante", "toggle-floating"], ["Alternar pantalla completa", "toggle-fullscreen"], ["Fijar", "toggle-pin"], ["Abrir reglas", "open-rules"],
                  ["Deshacer", "undo"], ["Recordar", "remember"]
                ]
                delegate: Rectangle {
                  width: actionText.implicitWidth + 20
                  height: 30
                  radius: 7
                  color: actionMouse.containsMouse ? Util.alpha(Color.accent, 0.30) : Util.alpha(Color.foreground, 0.09)
                  Text {
                    id: actionText
                    anchors.centerIn: parent
                    text: modelData[0]
                    color: Color.foreground
                    font.family: Style.font.family
                    font.pixelSize: 11
                  }
                  MouseArea {
                    id: actionMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.action(modelData[1])
                  }
                }
              }
            }

            Row {
              visible: root.phase === "confirm"
              spacing: 8
              Rectangle {
                width: 112; height: 32; radius: 7; color: Color.accent
                Text { anchors.centerIn: parent; text: "Recordar"; color: Color.background; font.family: Style.font.family; font.bold: true; font.pixelSize: 12 }
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: root.saveRememberedRule() }
              }
              Rectangle {
                width: 88; height: 32; radius: 7; color: Util.alpha(Color.foreground, 0.12)
                Text { anchors.centerIn: parent; text: "Cancelar"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: 12 }
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: root.phase = "inspect" }
              }
            }

            Text {
              width: parent.width
              text: root.status
              color: Util.alpha(Color.foreground, 0.65)
              font.family: Style.font.family
              font.pixelSize: 11
              wrapMode: Text.Wrap
              textFormat: Text.PlainText
            }
          }
        }
      }

      Rectangle {
        id: diagnosticCard
        visible: root.phase === "shortcut" || root.phase === "status"
        z: 3
        width: Math.min(520, parent.width - 36)
        height: Math.min(diagnosticContent.implicitHeight + 34, parent.height - 36)
        anchors.centerIn: parent
        radius: 14
        color: Util.alpha(Color.background, 0.98)
        border.width: 1
        border.color: Util.alpha(Color.accent, 0.82)

        Flickable {
          anchors.fill: parent
          anchors.margins: 17
          contentWidth: width
          contentHeight: diagnosticContent.implicitHeight
          clip: true
          Column {
            id: diagnosticContent
            width: parent.width
            spacing: 10
            Text { text: "OMAWHY"; color: Color.accent; font.family: Style.font.family; font.pixelSize: 12; font.bold: true; font.letterSpacing: 1.5 }
            Text {
              width: parent.width
              text: root.phase === "shortcut" ? "¿Por qué no funciona este atajo?" : "¿Está sano el escritorio?"
              color: Color.foreground
              font.family: Style.font.family
              font.pixelSize: 20
              font.bold: true
              wrapMode: Text.Wrap
            }
            Text {
              visible: root.phase === "shortcut"
              width: parent.width
              text: "Escríbelo como lo presionas: Super Shift I, Super Return, etc."
              color: Util.alpha(Color.foreground, 0.68)
              font.family: Style.font.family
              font.pixelSize: 12
              wrapMode: Text.Wrap
            }
            Ui.TextField {
              id: shortcutInput
              visible: root.phase === "shortcut"
              width: parent.width
              placeholderText: "Ejemplo: Super Shift I"
              onAccepted: root.inspectShortcut()
            }
            Rectangle {
              visible: root.phase === "shortcut"
              width: 96; height: 31; radius: 7; color: shortcutButton.containsMouse ? Util.alpha(Color.accent, 0.82) : Color.accent
              Text { anchors.centerIn: parent; text: "Revisar"; color: Color.background; font.family: Style.font.family; font.pixelSize: 12; font.bold: true }
              MouseArea { id: shortcutButton; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: root.inspectShortcut() }
            }
            Text {
              visible: root.phase === "status"
              width: parent.width
              text: "Esto revisa si la configuración activa existe, si Hyprland y Quickshell responden, y si el atajo de OmaWhy está definido."
              color: Util.alpha(Color.foreground, 0.68)
              font.family: Style.font.family
              font.pixelSize: 12
              wrapMode: Text.Wrap
            }
            Rectangle {
              visible: root.phase === "status"
              width: 110; height: 31; radius: 7; color: statusButton.containsMouse ? Util.alpha(Color.accent, 0.82) : Color.accent
              Text { anchors.centerIn: parent; text: "Revisar otra vez"; color: Color.background; font.family: Style.font.family; font.pixelSize: 12; font.bold: true }
              MouseArea { id: statusButton; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: root.inspectDesktop() }
            }
            Rectangle {
              visible: root.diagnostic.message !== undefined
              width: parent.width
              height: resultText.implicitHeight + 20
              radius: 9
              color: Util.alpha(Color.foreground, 0.08)
              Text {
                id: resultText
                anchors.fill: parent
                anchors.margins: 10
                text: root.diagnostic.message || ""
                color: Color.foreground
                font.family: Style.font.family
                font.pixelSize: 13
                wrapMode: Text.Wrap
                textFormat: Text.PlainText
              }
            }
            Repeater {
              visible: root.phase === "status"
              model: root.diagnostic.checks || []
              delegate: Rectangle {
                width: diagnosticContent.width
                height: checkText.implicitHeight + 18
                radius: 8
                color: modelData.state === "ok" ? Util.alpha(Color.accent, 0.12) : Util.alpha(Color.foreground, 0.10)
                Text {
                  id: checkText
                  anchors.fill: parent
                  anchors.margins: 9
                  text: (modelData.state === "ok" ? "✓ " : "! ") + modelData.label + "\n" + modelData.detail
                  color: Color.foreground
                  font.family: Style.font.family
                  font.pixelSize: 12
                  lineHeight: 1.2
                  wrapMode: Text.Wrap
                  textFormat: Text.PlainText
                }
              }
            }
            Text {
              visible: root.phase === "shortcut" && root.diagnostic.binding !== undefined
              width: parent.width
              text: "Definido en " + String(root.diagnostic.binding.path || "").split("/").pop() + ", línea " + root.diagnostic.binding.line + "."
              color: Util.alpha(Color.foreground, 0.68)
              font.family: Style.font.family
              font.pixelSize: 11
              wrapMode: Text.Wrap
            }
            Text {
              visible: root.phase === "shortcut" && root.diagnostic.events !== undefined && root.diagnostic.events.length > 0
              text: "Abrir archivo"
              color: Color.accent
              font.family: Style.font.family
              font.pixelSize: 12
              font.underline: shortcutSourceMouse.containsMouse
              MouseArea { id: shortcutSourceMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: root.openShortcutSource() }
            }
            Text {
              text: "Volver"
              color: Color.accent
              font.family: Style.font.family
              font.pixelSize: 12
              font.underline: backMouse.containsMouse
              MouseArea { id: backMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: root.open() }
            }
            Text { width: parent.width; text: root.status; color: Util.alpha(Color.foreground, 0.65); font.family: Style.font.family; font.pixelSize: 11; wrapMode: Text.Wrap; textFormat: Text.PlainText }
          }
        }
      }
    }
  }
}
