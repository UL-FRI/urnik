var colorTab = new Array("#FFFFFF","#FFFF00","#FF0000", "#00FF00");
var hideTab = new Array(true, false, true, false);

var maxHated = 5;

function showOrHide(cell){
    cell.levelField.style.display ='none';
    if (hideTab[cell.levelField.selectedIndex]){
        cell.weightField.style.display = 'none';
    } else {
        cell.weightField.style.display = 'none';
        //cell.weightField.style.display = 'inline';
    }
    cell.bgColor = colorTab[cell.levelField.selectedIndex];
}

function preferenceOnClick(event)
{
    cellClicked(event.currentTarget);
}


// Gets unwanted (Yellow) (Backend "HATES") cells
function getUnwantedCells(){
    let total = 0;
    [...document.getElementsByTagName("td")].forEach(function(cell){
        try{
            if (cell.levelField.selectedIndex == 1){
                total++;
            }
        } catch(e){
            // Might be one of the header cells that have no levelField defined. 
        }
    })
    return total;
}

function cellClicked(cell)
{
    var si = cell.levelField.selectedIndex;
    si = (si + 1) % cell.levelField.options.length;
    if(si == 1){
        if (getUnwantedCells() > maxHated-1){
            si = (si + 1) % cell.levelField.options.length;
        }
    }

    cell.levelField.selectedIndex = si;
    cell.weightField.value = "1.0";
    if ((si == 1) && (cell.weightField.value == '')){
        cell.weightField.value = "1.0"
    }
    showOrHide(cell)
}

function preferenceDayClickEvent(event) {
    var thIndex = $(this).index()+1;
    $("table td:nth-child("+ thIndex +")").each(function(){
        cellClicked($(this)[0]);
    });
}

function makePrettyPreference(index, inElt){
    var p = inElt.parentNode;
    p.weightField = inElt;
    p.levelField = p.getElementsByTagName("select")[0];
    showOrHide(p);
    p.weightField.onclick = function(event){event.stopPropagation ();};
    p.onclick = preferenceOnClick;
}


function next_id(s){
    var e2 = s.lastIndexOf('-')
    var s2 = s.substring(e2, s.length)
    var s1 = s.substring(0, e2-1)
    var e1 = s1.lastIndexOf('-')
    var v = s.substring(e1+1, e2)// (parseInt(v, 10)+1)
    return s1 + (parseInt(v, 10)+1)  + s2
}

function showCorrectGroups(p){
    p.find("select.realization_group_select").each(function (idx, elt){
        var e = $(elt)
        var pe = p.get(0)
        if (e.parent().get(0) != pe.extraForm){
            $(e).find('option').remove();
            $(pe.extraForm).find('select.realization_group_select>option').each(function(j, o){
                var v = $(o).val()
                if (v in pe.setOptions){
                    if (pe.setOptions[v] == elt){
                        n = $(o).clone(true)
                        n.attr('selected', 'selected')
                        e.append(n)
                    }
                } else {
                    e.append($(o).clone(true))
                }
            })
        }
    })
}

function addRealization(event){
    var delButton = $(event.currentTarget)
    delButton.checked = true
    var p = delButton.parent()
    var n = $(p.get(0).extraForm).clone(true)
    var nf = p.children('[name$="TOTAL_FORMS"]').first()
    nf.val(1 + parseInt(nf.val(), 10))
    n.removeClass("extra_realization")
    n.addClass("realization")
    n.children(".realization_delete").attr("checked", false)
    var pr = $(event.currentTarget).prev()
    n.insertAfter(pr)
    showCorrectGroups(n.parent())
    n.show()
    var inputs = Array("id", "groups", "teachers", "activity", "DELETE") 
    for (i in inputs){
        var t = '[name$="'+ inputs[i] + '"]'
        var arg_in = pr.children(t).first()
        var arg_out = n.children(t).first()
        var s = next_id(arg_in.attr("id"))
        arg_out.attr("id", s)
        s = next_id(arg_in.attr("name"))
        arg_out.attr("name", s)
    }
}

function removeRealization(event){
    var button = $(event.currentTarget)
    var realization = button.parent()
    realization.find("select.realization_group_select option").each(function(i, elt){
        e = $(elt)
        e.attr("selected", "")
        realization.parent().get(0).setOptions.splice(e.val())
    })
    button.attr('checked', true)
    realization.hide()
    showCorrectGroups(realization.parent())
}

function groupSelect(event) {
    var oopt = $(event.currentTarget) 
    var sel = oopt.parent()
    var r = sel.parent()
    var p = r.parent()
    var pe = p.get(0)
    selt = sel.get(0)
    if (oopt.attr('selected')){
        pe.setOptions[oopt.val()] = selt;
    } else {
        pe.setOptions.splice(oopt.val())
    }
    showCorrectGroups(p)
}


function preferenceInit(){
    $(".TTablePrefWeight").each(makePrettyPreference);
    $("th.day").click(preferenceDayClickEvent);
}


$(document).ready(function(){
    preferenceInit()
})
