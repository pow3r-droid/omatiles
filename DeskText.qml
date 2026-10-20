import QtQuick
// Text that never reads markup. Qt guesses rich text from a tag anywhere in a string,
// and store entries, calendar events and remote machines all supply their own text.
Text {
    textFormat: Text.PlainText
}
