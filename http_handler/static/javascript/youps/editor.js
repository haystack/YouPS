var datatable_config = {
    "bPaginate": false,
    "bLengthChange": false,
    "bFilter": true,
    "bInfo": false,
    "bAutoWidth": false,
    "searching": false,
    "columns": [
        { "width": "40px", "orderable": false },
        null,
        { "width": "300px" },
        null
    ],
    "language": {
        "emptyTable": 'Click "Debug my code" to test your rule',
      },
    "order": [[1, 'asc']]
};
var debugging_messages_ids = [];
var line_widgets = [];
var inspect = {};

function init_editor(editor_elem) {
    var editor = CodeMirror.fromTextArea(editor_elem, {
        mode: {name: "python",
            version: 2,
            singleLineStringErrors: false},
        lineNumbers: true,
        matchBrackets: true,
        indentUnit: 4,
        gutters: ["breakpoints"],
        lint: true,
        lineWrapping:'true'
    });

    var arrows = [13, 27, 37, 38, 39, 40];
    editor.on("keyup", function(cm, e) {
      if (arrows.indexOf(e.keyCode) < 0) {
        editor.execCommand("autocomplete")
      }
    })

    // Add debugging interfaces 
    editor.on("gutterClick", function(cm, n) {
        var line_number = n +1;
        
        var required_new = !$(cm.getWrapperElement()).find(".CodeMirror-line:eq({0})".format(n)).hasClass('selected');

        // Update gutter and highlight the selected line
        $(cm.getWrapperElement()).find(".CodeMirror-line").removeClass("selected");
        $(cm.getWrapperElement()).find(".CodeMirror-gutter-wrapper").removeClass("selected");
        $(cm.getWrapperElement()).parents(".panel[rule-id]").find('.debugger-container tr').removeClass('selected');

        if(required_new) {
            $(cm.getWrapperElement()).find(".CodeMirror-line:eq({0})".format(n)).addClass("selected");
            $(cm.getWrapperElement()).find(".CodeMirror-gutter-wrapper:eq({0})".format(n)).addClass("selected");

            // filter examples 
            $(cm.getWrapperElement()).parents(".panel[rule-id]").find('.debugger-container tr[line-number{0}]'.format(line_number)).addClass('selected');
        }
      });
      
    // editor.getValue( "import re, spacy, datetime, arrow" );
    editor.markText({line:0,ch:0},{line:1,ch:1},{readOnly:true});

    editor.on('change',function(cm){
        // get value right from instance
        $(cm.getWrapperElement()).parents(".panel[rule-id]").find('.btn-debug-update').addClass('glow');

    });

    // debugging inspector
    $("#editor-container").on("click", ".debugger-container .detail-inspect", function() {
        trackOutboundLink('debug - detail');
        // $(this).attr("msg-id") // call simulate value
        $(this).parents("table").find("button").removeClass("detail-viewing");
        $(this).addClass("detail-viewing");
        
        // Remove line widgets
        for (var i = 0; i < line_widgets.length; ++i) {
            $(this).parents('div[rule-id]').find('.CodeMirror')[0].CodeMirror.removeLineWidget(line_widgets[i]);
        }
        line_widgets = [];

        var logs = inspect[$(this).attr("msg-id")];
        for(var i = 0; i < logs.length;i++) {
            if(logs[i]["type"] != "get" && logs[i]["type"] != "set")
                continue
            
            var node = document.createElement('div')
            var display = document.createElement('div')
            
            node.appendChild(display)
            
            if(logs[i]["type"] == "get") {
                display.innerText = "{0}.{1}: {2}".format(logs[i]["class_name"], logs[i]["function_name"], logs[i]["args"][0])
                display.style.backgroundColor = 'lightgray' || 'lightyellow'
            }
            else {
                display.innerText = "{0}.{1}: {2}->{3}".format(logs[i]["class_name"], logs[i]["function_name"], logs[i]["args"][0], logs[i]["args"][1])
                display.style.backgroundColor = 'lightyellow'
            }
            
            display.style.padding = '5px'
            // node.style.height = '20px'
    
            var w = $(this).parents('div[rule-id]').find('.CodeMirror')[0].CodeMirror.addLineWidget(logs[i]["line_number"]-1, node);
    
            line_widgets.push(w);
            
        }
    }); 
    
}

function extract_shortcut_argument($container) {
    var args = [];
    $container.find('.instruction-container ul li').each(function (index, elem) {
        var args_name = $(elem).find(".args-name").val() || "";
        var args_type = $(elem).find("select").val();

        args.push({"name": args_name, "type": args_type})
    })
    return args;
}

function extract_rule_code(container) {
    var editors = [];

    $(container).find('.CodeMirror').each( function(index, elem) {
        if( $(elem).parents('.panel').hasClass('removed') ) return;
        var code = elem.CodeMirror.getValue();
        var $parent_container = $(elem).parents('.panel');
        var uid = $parent_container.attr('rule-id');
        var name = $parent_container.find('.panel-title input').val();
        var type = $(elem).parents('.editable-container').attr('type');

        // Extract if there is interval, then attach the timespan to the type value
        if(type=="new-message" && $parent_container.find('.trigger input:checked').attr('value') != "now") {
            var time_span = $parent_container.find('.trigger input:checked').next().val();
            time_span = parseInt(time_span) || 1;
            var time_unit = $parent_container.find('.trigger input:checked').next().next().val();
            if(time_unit == "min") time_span *= 60;
            else if(time_unit == "hr") time_span *= (60*60);
            else time_span *= (60*60*24);
            type += ("-" + time_span);
        }
        

        var selected_folders = [];
        $(elem).parents('.panel').find(".folder-container input:checked").each(function () {
            selected_folders.push($(this).attr('value'));
        });

        var args = [];
        // Get params
        if( type == "shortcut" ) {
            args=extract_shortcut_argument($parent_container);
        }

        editors.push({"uid": uid, "name": name, "code": $.trim( code ).replace('\t', "    "), "type": type, "folders": selected_folders, "args": args}); 
    })

    return editors;
}

function show_loader( is_show ) {
    if(is_show) $(".sk-circle").show();
    else $(".sk-circle").hide();
}

function remove_rule(rule_uid) {
    show_loader(true);

    var params = {
        'rule-id' : rule_uid
    };

    $.post('/remove_rule', params,
        function(res) {
            show_loader(false);
            console.log(res);
            
            // Auth success
            if (res.status) {

                if (res.code) { 
                }
                else {                        
                    notify(res, true);
                }
            }
            else {
                notify(res, false);
            }
        }
    );
}


function run_simulate_on_messages(folder_name, N, editor_rule_container, extra_info={}) {
    show_loader(true);

    var params = {
        'folder_name': folder_name,
        'N': N,
        'user_code': $.trim( $(editor_rule_container).find('.CodeMirror')[0].CodeMirror.getValue() ),
        'extra_info': JSON.stringify(extra_info)
        // TODO if message_ids is not given, run simulation on recent messages on folders
        // 'message_ids': JSON.stringify(msgs_id)
    };

    $.post('/run_simulate_on_messages', params,
        function(res) {
            show_loader(false);
            console.log(res);
            
            // get simulation result
            if (res.status) {
                $(editor_rule_container).find('.btn-debug-update').removeClass('glow');
                var dt_elem = $(editor_rule_container).find('.debugger-container table')[0];
                var t = $( dt_elem ).DataTable();
                // delete all before added new 
                $.each($(dt_elem).find('tr[folder]'), function(index, elem) {
                    if(N> 0 || folder_name.includes($(elem).attr('folder')))
                        t.row( elem ).remove().draw();  
                })

                $.each( res['messages'], function( msg_id, value ) {
                    var Message = value;

                    var json_panel_id = Math.floor(Math.random() * 10000) + 1;
                    debugger;
                    var added_row = t.row.add( [
                        '<div class="jsonpanel contact" id="jsonpanel-from-{0}"></div>'.format(json_panel_id),
                        '<div class="jsonpanel" id="jsonpanel-{0}"></div>'.format(json_panel_id),
                        '{0}'.format(Message["log"].replace(/\n/g , "<br>")),
                        '<button msg-id={0} class="detail-inspect"></button>'.format(msg_id)
                        // '{1}  <button msg-id={0} class="detail-inspect"></button>'.format(msg_id, Message["log"])
                    ] ).draw( false ).node();

                    inspect[msg_id]= Message["property_log"];
                    

                    $( added_row ).attr('folder', Message['folder'])
                        .attr('msg-id', msg_id)
                        .attr('line-number2', 1);
                        
                        // .attr('line-number{0}', 1); // TODO add activated line
                    if(Message["error"])
                        $( added_row ).find("td:eq(2)").addClass("error");
                    // else $( added_row ).find("td:eq(2)").addClass(json_panel_id % 2 == 0? "warning":""); 
                    if(json_panel_id % 2 == 0) $( added_row ).attr('line-number3', 1);     

                    // Delete attributes that are not allowed for users 
                    delete Message["property_log"];
                    delete Message["trigger"];
                    delete Message["error"];
                    delete Message["log"];
                    delete Message["timestamp"];
                    delete Message["type"];

                    $('#jsonpanel-from-' + json_panel_id).jsonpanel({
                        data: {
                            Contact :  Message['from_'] || []
                        }
                    });
    
                    if (Message['from_'])
                        // set contact object preview 
                        $('#jsonpanel-from-' + json_panel_id + " .val-inner").text(
                            '"{0}", '.format(Message['from_']['name']) + '"{0}", '.format(Message['from_']['email'])  + '"{0}", '.format(Message['from_']['organization'])  + '"{0}", '.format(Message['from_']['geolocation'])  );
        
                    
                    $('#jsonpanel-' + json_panel_id).jsonpanel({
                        data: {
                            Message : Message
                        }
                    });
    
                    // set msg object preview 
                    var preview_msg = '{0}: "{1}", '.format("subject", Message['subject']) +  '{0}: "{1}", '.format("folder", Message['folder']);
                    for (var key in Message) {
                        if (Message.hasOwnProperty(key)) {
                            preview_msg += '{0}: "{1}", '.format(key, Message[key])
                        }
                    }
                    $("#jsonpanel-" + json_panel_id + " .val-inner").text( preview_msg );
                  });      
            }

            // Save the code as well    
            run_code( $('#test-mode[type=checkbox]').is(":checked"), $("#btn-code-submit") ? $("#btn-code-submit").hasClass('active'): true, true ); 
        }
    );
}

var debug_matched_row = [];


document.addEventListener("mv-load", function(e){   
    // Init editor & its autocomplete
    if(e.srcElement.id != "apis-container") return;

    // Editor autocomplete
    var global_method = [];
    document.querySelectorAll('#apis-container div[property="folder"] h4').forEach(function(element) {
        var func_with_param = element.innerHTML.split(")")[0] + ")";
        func_with_param = $.trim(func_with_param.replace(" (", "("));
        global_method.push( {"text": func_with_param, "displayText": func_with_param + ": " + $(element).siblings("span").text() });
    });

    var entity_method = [];
    document.querySelectorAll('#apis-container div[property="message"] h4').forEach(function(element) {
        var func_with_param = $.trim(element.innerHTML.replace(" (", "("));
        entity_method.push( {"text": func_with_param, "displayText": func_with_param + ": " + $(element).siblings("span").text()} );
    });

    document.querySelectorAll('#apis-container div[property="contact"] h4').forEach(function(element) {
        var func_with_param = $.trim(element.innerHTML.replace(" (", "("));
        entity_method.push( {"text": func_with_param, "displayText": func_with_param + ": " + $(element).siblings("span").text()});
    });

    // document.querySelectorAll('#apis-container div[property="calendar"] h4').forEach(function(element) {
    //     entity_method.push( $.trim(element.innerHTML.split("(")[0]) );
    // });

    CodeMirror.registerHelper('hint', 'dictionaryHint', function(editor, options) {
        var cur = editor.getCursor();
        var curLine = editor.getLine(cur.line);
        var start = cur.ch;
        var end = start;

        while (end < curLine.length && /[\w|\\.]/.test(curLine.charAt(end))) ++end;
        while (start && /[\w]/.test(curLine.charAt(start - 1))) --start;
        var curWord = start !== end && curLine.slice(start, end);
        var regex = new RegExp('^' + curWord, 'i');
        
        console.log(entity_method)
        console.log(global_method)
        
        var suggestion = curLine.includes(".") ? 
            entity_method.filter(function(item) {
                return item["text"].match(regex);
            }).sort() : 
            global_method.filter(function(item) {
                return item["text"].match(regex);
            }).sort();
        
        // Showing all the possible method/property of the object
        curLine = $.trim(curLine);
        if ( curLine[curLine.length -1] == ".") suggestion = entity_method;
        console.log(suggestion);
        suggestion.length == 1 ? suggestion.push(" ") : console.log();

        return {
            list: suggestion,
            from: CodeMirror.Pos(cur.line, start),
            to: CodeMirror.Pos(cur.line, end)
        }
    });

    CodeMirror.commands.autocomplete = function(cm) {
        CodeMirror.showHint(cm, CodeMirror.hint.dictionaryHint);
    };

    // Hide body until editor is ready
    setTimeout(() => {
        $('#loading-wall').hide();
        show_loader(false);
    }, 500);
});
// gutter Hover 
// $("body").on("mouseenter", ".CodeMirror-gutter-wrapper", function() {
//     var cm = $(this).parents('.CodeMirror')[0].CodeMirror;
//     var cnt = 0;
//     while(cm.getLine(cnt++)) {
//         var info = cm.lineInfo(cnt-1);
//         if( !info.gutterMarkers )
//             cm.setGutterMarker(cnt-1, "breakpoints", makeMarker());
//     }

//     var line_number = $(".CodeMirror-gutter-wrapper").index(this) + 1;

//     // highlight the email matched at the line
//     // add .selected temporarily to matched example messages, then will be removed when mouse leaves
//     $(this).parents(".panel[rule-id]").find('tr[line-number{0}]'.format(line_number)).addClass('hover-selected');
// })

// $("body").on("mouseleave", ".CodeMirror-gutter-wrapper", function() {
//     var line_number = $(".CodeMirror-gutter-wrapper").index(this) + 1;

//     // remove .selected from the matched example messages
//     var $root_elem = $(this).parents(".panel[rule-id]");
//     $root_elem.find('.debugger-container tr[line-number{0}]'.format(line_number)).removeClass('hover-selected');
// })

// Accordion listener
$("#editor-container").on("click", ".panel-heading", function (e) {
    e.preventDefault();

    // Fire only by panel click not child
    if($(e.target).is('input') || $(e.target).is('button')) return;

    var $this = $(this);
    if(!$this.hasClass('panel-collapsed')) { // close the panel
        $this.parents('.panel').find('.panel-body').slideUp();
        $this.addClass('panel-collapsed');
        $this.find('.fa-chevron-down').hide();
		$this.find('.fa-chevron-up').show();
					
		var selected_folders = [];
		$this.parents(".flex_container").siblings('.panel-body').find(".folder-container input:checked").each(function () {
			selected_folders.push( $(this).attr('value') );
		});
		$this.find(".preview-folder").text( selected_folders.join(", ") );

        $this.find(".preview-folder").show();
    } else { // open the panel
        $this.parents('.panel').find('.panel-body').slideDown();
        $this.removeClass('panel-collapsed');
        $this.find('.fa-chevron-up').hide();
        $this.find('.fa-chevron-down').show();
        $this.find(".preview-folder").hide();
    }
})

// add a new editor
$("#editor-container").on("click", ".btn-new-editor", function() {
    var type = $(this).parents('.panel-title').find("option:selected").val();
    if(!type) type="shortcut";
    debugger;
    trackOutboundLink('new editor -' + type);
    
    var $container = $( $(this).parents(".tab-content").find(".editable-container[type='{0}']".format(type)) );
    if(type == "shortcut")
        $container = $(".editable-container");
    var editor_elem = load_rule(false, type, $container);
});

// remove / revive an editor
$("#editor-container").on("click", ".editable-container .flex_item_left", function() {
    trackOutboundLink('remove editor -' + $(this).attr("type"));
    if ($(this).parents('.panel').hasClass('removed')) {
        $(this).parents('.panel').removeClass('removed');
        run_code( $('#test-mode[type=checkbox]').is(":checked"), $("#btn-code-submit")? $("#btn-code-submit").hasClass('active') : null); 
        

        // give different visual effects
        $(this).find('svg').remove();
        $(this).append('<i class="fas fa-trash fa-3x"></i>');
        
    }else {
        if(!$(this).siblings('.flex_item_right').hasClass("panel-collapsed") ) // if opened
            $(this).siblings('.flex_item_right').click(); // then close 

        // remove editor from the server
        var rule_id = $(this).parents('.panel').attr('rule-id');
        remove_rule(rule_id);

        $(this).parents('.panel').addClass('removed');

        // give different visual effects
        $(this).find('svg').remove();
        $(this).append('<i class="fas fa-redo fa-3x"></i>');
        
    }
    
});