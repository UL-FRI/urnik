from xml.dom.minidom import Document

# Create XML from array.
# Array structure:
# - [parent, dictionary, [children], parent, dictionary, [children], ...]


def create_xml(array, doc=None, current=None):
    if doc is None:
        doc = Document()

    if current is None:
        current = doc

    while len(array) >= 3:
        name = array[0]
        properties = array[1]
        children = array[2]
        # print name
        # print properties
        # print children

        array = array[3:]

        elt = doc.createElement(name)
        for name, value in properties.items():
            elt.setAttribute(name, value)

        create_xml(children, doc, elt)
        current.appendChild(elt)

    return doc
