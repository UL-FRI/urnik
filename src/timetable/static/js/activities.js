function next_id(s){
    var e2 = s.lastIndexOf('-');
    var s2 = s.substring(e2, s.length);
    var s1 = s.substring(0, e2);
    var e1 = s1.lastIndexOf('-');
    var s1 = s1.substring(0, e1+1);
    var v = s.substring(e1+1, e2)
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

function setOptimalWidth(p) {
    var  maxWidth = 0
    p.find("div.realization").each(function (idx, elt){
        var e = $(elt)
        var width = e.width();
        if (width > maxWidth) {
          maxWidth = width;
        }
    })
    var optimalWidth = maxWidth
    p.find("div.realization").each(function (idx, elt){
        var e = $(elt)
        e.width(optimalWidth);
    })
}

function colorTables() {
	$("table.headteacher_cycles tr").filter(function() {
	  return $(this).children().length == 6;
	}).filter(':even').addClass('alternateTableColor');
		
	$("table.assistantteacher_cycles tr").filter(function() {
	  return $(this).children().length == 6;
	}).filter(':even').addClass('alternateTableColor');	
	
	$("tr.alternateTableColor td[rowspan]").each(function() {
	  $(this).parent().nextAll().slice(0, this.rowSpan - 1).addClass('alternateTableColor');
	});
}

function addRealization(event){
    var delButton = $(event.currentTarget)
    delButton.checked = true
    var p = delButton.parent()
    var n = $(p.get(0).extraForm).clone(true)
    var nf = p.children('[name$="TOTAL_FORMS"]').first()
    nf.val(parseInt(nf.val(), 10) + 1)
    n.removeClass("extra_realization")
    n.addClass("realization")
    n.children(".realization_delete").attr("checked", false)
    var pr = $(event.currentTarget).prev()
    n.insertAfter(pr)
    showCorrectGroups(n.parent())
    setOptimalWidth(n.parent())
    n.show()
    n.removeAttr("style")
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
    var parent = realization.parent().get(0)
    realization.find("select.realization_group_select option").each(function(i, elt){
        e = $(elt)
        e.attr("selected", "")
        if (parent.setOptions.hasOwnProperty(e.val())){
            delete parent.setOptions[e.val()]
        }
    })
    realization.find("select.realization_teacher_select option").each(function(i, elt){
        var activity_id = this.parentElement.name.split("--")[1];
        var teacher_id = this.value;
	if (this.selected) changeTeacherCycles(teacher_id, activity_id, -1)
	 
    })
    button.attr('checked', true)
    realization.hide()
    showCorrectGroups(realization.parent())
    setOptimalWidth(realization.parent())
    
}

function groupSelect(event) {
    var sel = $(event.currentTarget) 
    var r = sel.parent()
    var p = r.parent()
    var pe = p.get(0)
    selt = sel.get(0)
    opts = selt.options
    for (i = 0; i < opts.length; i++){
        var oopt = $(opts[i])
        if (oopt.attr('selected')){
            pe.setOptions[oopt.val()] = selt;
        } else {
            delete pe.setOptions[oopt.val()]
        }
    }
    showCorrectGroups(p)
}



function changeTeacherCycles(teacher_id, lecture_type, increase) {
	var teacher_row = $("#type_" + lecture_type + "_teacher_" + teacher_id)
	var realization_span = jQuery(teacher_row).find("span.nrealizations");
	var current_realization_num = parseInt(realization_span.get(0).innerHTML)
	realization_span.get(0).innerHTML = current_realization_num + increase
}


function teacherSelect(event) {
    var select_element_id = this.id
    var select_element = $("#" + select_element_id)
    var select_element_html = this
    var previous_value_key = "previous_value"
    var activity_id = select_element_html.name.split("--")[1] 
    var realization_div = select_element.parent()
    var lecture_type = realization_div.attr('class').split(' ')[1]
    
    if (!(previous_value_key in select_element_html))  {
      select_element_html[previous_value_key] = {}
      select_element.find("option").each(function(index) { select_element_html[previous_value_key][this.value] = this.defaultSelected });
    }    
    select_element.find("option").each(function(index) { 
      if (this.selected != select_element_html[previous_value_key][this.value] ) {
	changeTeacherCycles(this.value, lecture_type, this.selected ? 1:-1)
	select_element_html[previous_value_key][this.value] = this.selected
      }
    });
}


function activityInit(){
    $(".realization_delete").click(removeRealization)
    $(".extra_realization").each(function(i, elt){
        var p = $(elt).parent()
        var ep = p.get(0)
        ep.setOptions = new Object();
        ep.extraForm = elt;
    })
    $(".realization>select.realization_group_select").each(function(i, elt){
        var e = $(elt)
        var p = e.parent().parent().get(0)
        e.find("option").each(function(j, o){
            o = $(o)
            if (o.attr('selected')){
                p.setOptions[o.val()] = elt
            }
        })
    })
    $(".extra_realization").hide();
    $("div.realization:parent").each(function(i, elt){
        showCorrectGroups($(elt).parent())
        setOptimalWidth($(elt).parent())
    })
    /* For the first newly created realization form to have the correct name and id, */
    /* the hidden extra form also needs to have "realization" as it's class. */
    $(".extra_realization").addClass("realization");
    $(".extra_realization>.realization_delete").attr("checked", true); 
    $(".extra_realization").val(true);
    $(".realization_teacher_select").change(teacherSelect);
    $(".realization_group_select").change(groupSelect);
    $(".add_realization").click(addRealization);
    colorTables();
}

$(document).ready(function(){
    activityInit()
})
