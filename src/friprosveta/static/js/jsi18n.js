

(function (globals) {

  var django = globals.django || (globals.django = {});

  
  django.pluralidx = function (n) {
    var v=(n%100==1 ? 0 : n%100==2 ? 1 : n%100==3 || n%100==4 ? 2 : 3);
    if (typeof(v) == 'boolean') {
      return v ? 1 : 0;
    } else {
      return v;
    }
  };
  

  
  /* gettext library */

  django.catalog = {
    "%(sel)s of %(cnt)s selected": [
      "%(sel)s od %(cnt)s izbranih", 
      "%(sel)s od %(cnt)s izbran", 
      "%(sel)s od %(cnt)s izbrana", 
      "%(sel)s od %(cnt)s izbrani"
    ], 
    "6 a.m.": "Ob 6h", 
    "Available %s": "Mo\u017ene %s", 
    "Calendar": "Koledar", 
    "Cancel": "Prekli\u010di", 
    "Choose": "Izberi", 
    "Choose a time": "Izbor \u010dasa", 
    "Choose all": "Izberi vse", 
    "Chosen %s": "Izbran %s", 
    "Click to choose all %s at once.": "Kliknite za izbor vseh %s hkrati.", 
    "Click to remove all chosen %s at once.": "Kliknite za odstranitev vseh %s hkrati.", 
    "Clock": "Ura", 
    "Filter": "Filtriraj", 
    "Hide": "Skrij", 
    "January February March April May June July August September October November December": "Januar Februar Marec April Maj Junij Julij Avgust September Oktober November December", 
    "Midnight": "Polno\u010d", 
    "Noon": "Opoldne", 
    "Now": "Takoj", 
    "Remove": "Odstrani", 
    "Remove all": "Odstrani vse", 
    "S M T W T F S": "N P T S \u010c P S", 
    "Show": "Prika\u017ei", 
    "This is the list of available %s. You may choose some by selecting them in the box below and then clicking the \"Choose\" arrow between the two boxes.": "To je seznam mo\u017enih %s. Izbrane lahko izberete z izbiro v spodnjem okvirju in s klikom na pu\u0161\u010dico \"Izberi\" med okvirjema.", 
    "This is the list of chosen %s. You may remove some by selecting them in the box below and then clicking the \"Remove\" arrow between the two boxes.": "To je seznam mo\u017enih %s. Odve\u010dne lahko odstranite z izbiro v okvirju in klikom na pu\u0161\u010dico \"Odstrani\" med okvirjema.", 
    "Today": "Danes", 
    "Tomorrow": "Jutri", 
    "Type into this box to filter down the list of available %s.": "Z vpisom niza v to polje, zo\u017eite izbor %s.", 
    "Yesterday": "V\u010deraj", 
    "You have selected an action, and you haven't made any changes on individual fields. You're probably looking for the Go button rather than the Save button.": "Izbrali ste dejanje, vendar niste naredili nobenih sprememb na posameznih poljih. Verjetno i\u0161\u010dete gumb Pojdi namesto Shrani.", 
    "You have selected an action, but you haven't saved your changes to individual fields yet. Please click OK to save. You'll need to re-run the action.": "Izbrali ste dejanje, vendar niste shranili sprememb na posameznih poljih. Kliknite na 'V redu', da boste shranili. Dejanje boste morali ponovno izvesti.", 
    "You have unsaved changes on individual editable fields. If you run an action, your unsaved changes will be lost.": "Na nekaterih poljih, kjer je omogo\u010deno urejanje, so neshranjene spremembe. V primeru nadaljevanja bodo neshranjene spremembe trajno izgubljene."
  };

  django.gettext = function (msgid) {
    var value = django.catalog[msgid];
    if (typeof(value) == 'undefined') {
      return msgid;
    } else {
      return (typeof(value) == 'string') ? value : value[0];
    }
  };

  django.ngettext = function (singular, plural, count) {
    var value = django.catalog[singular];
    if (typeof(value) == 'undefined') {
      return (count == 1) ? singular : plural;
    } else {
      return value[django.pluralidx(count)];
    }
  };

  django.gettext_noop = function (msgid) { return msgid; };

  django.pgettext = function (context, msgid) {
    var value = django.gettext(context + '\x04' + msgid);
    if (value.indexOf('\x04') != -1) {
      value = msgid;
    }
    return value;
  };

  django.npgettext = function (context, singular, plural, count) {
    var value = django.ngettext(context + '\x04' + singular, context + '\x04' + plural, count);
    if (value.indexOf('\x04') != -1) {
      value = django.ngettext(singular, plural, count);
    }
    return value;
  };
  

  django.interpolate = function (fmt, obj, named) {
    if (named) {
      return fmt.replace(/%\(\w+\)s/g, function(match){return String(obj[match.slice(2,-2)])});
    } else {
      return fmt.replace(/%s/g, function(match){return String(obj.shift())});
    }
  };


  /* formatting library */

  django.formats = {
    "DATETIME_FORMAT": "Y-m-d H:i", 
    "DATETIME_INPUT_FORMATS": [
      "%Y-%m-%d %H:%M:%S", 
      "%Y-%m-%d %H:%M:%S.%f", 
      "%Y-%m-%d %H:%M", 
      "%Y-%m-%d", 
      "%m/%d/%Y %H:%M:%S", 
      "%m/%d/%Y %H:%M:%S.%f", 
      "%m/%d/%Y %H:%M", 
      "%m/%d/%Y", 
      "%m/%d/%y %H:%M:%S", 
      "%m/%d/%y %H:%M:%S.%f", 
      "%m/%d/%y %H:%M", 
      "%m/%d/%y"
    ], 
    "DATE_FORMAT": "N j, Y", 
    "DATE_INPUT_FORMATS": [
      "%Y-%m-%d", 
      "%m/%d/%Y", 
      "%m/%d/%y", 
      "%b %d %Y", 
      "%b %d, %Y", 
      "%d %b %Y", 
      "%d %b, %Y", 
      "%B %d %Y", 
      "%B %d, %Y", 
      "%d %B %Y", 
      "%d %B, %Y"
    ], 
    "DECIMAL_SEPARATOR": ".", 
    "FIRST_DAY_OF_WEEK": "0", 
    "MONTH_DAY_FORMAT": "F j", 
    "NUMBER_GROUPING": "0", 
    "SHORT_DATETIME_FORMAT": "m/d/Y P", 
    "SHORT_DATE_FORMAT": "m/d/Y", 
    "THOUSAND_SEPARATOR": ",", 
    "TIME_FORMAT": "P", 
    "TIME_INPUT_FORMATS": [
      "%H:%M:%S", 
      "%H:%M:%S.%f", 
      "%H:%M"
    ], 
    "YEAR_MONTH_FORMAT": "F Y"
  };

  django.get_format = function (format_type) {
    var value = django.formats[format_type];
    if (typeof(value) == 'undefined') {
      return format_type;
    } else {
      return value;
    }
  };

  /* add to global namespace */
  globals.pluralidx = django.pluralidx;
  globals.gettext = django.gettext;
  globals.ngettext = django.ngettext;
  globals.gettext_noop = django.gettext_noop;
  globals.pgettext = django.pgettext;
  globals.npgettext = django.npgettext;
  globals.interpolate = django.interpolate;
  globals.get_format = django.get_format;

}(this));

