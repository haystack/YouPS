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
    // editor.markText({line:0,ch:0},{line:2,ch:1},{readOnly:true});

    editor.on('change',function(cm){
        // get value right from instance
        $(cm.getWrapperElement()).parents(".panel[rule-id]").find('.btn-debug-update').addClass('glow');
    });
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
            $parent_container.find('.instruction-container ul li').each(function (index, elem) {
                var args_name = $(elem).find(".args-name").val() || "";
                var args_type = $(elem).find("select").val();

                args.push({"name": args_name, "type": args_type})
            })
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

var debug_matched_row = [];

// gutter Hover 
$("body").on("mouseenter", ".CodeMirror-gutter-wrapper", function() {
    var cm = $(this).parents('.CodeMirror')[0].CodeMirror;
    var cnt = 0;
    while(cm.getLine(cnt++)) {
        var info = cm.lineInfo(cnt-1);
        if( !info.gutterMarkers )
            cm.setGutterMarker(cnt-1, "breakpoints", makeMarker());
    }

    var line_number = $(".CodeMirror-gutter-wrapper").index(this) + 1;

    // highlight the email matched at the line
    // add .selected temporarily to matched example messages, then will be removed when mouse leaves
    $(this).parents(".panel[rule-id]").find('tr[line-number{0}]'.format(line_number)).addClass('hover-selected');
})

$("body").on("mouseleave", ".CodeMirror-gutter-wrapper", function() {
    var line_number = $(".CodeMirror-gutter-wrapper").index(this) + 1;

    // remove .selected from the matched example messages
    var $root_elem = $(this).parents(".panel[rule-id]");
    $root_elem.find('.debugger-container tr[line-number{0}]'.format(line_number)).removeClass('hover-selected');
})

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
    trackOutboundLink('new editor -' + $(this).attr("type"));
    var $container = $( $(this).siblings("[type='{0}']".format($(this).attr("type"))) );
    var editor_elem = load_rule(false, $(this).attr("type"), $container);
});

// remove / revive an editor
$("#editor-container").on("click", ".editable-container .flex_item_left", function() {
    trackOutboundLink('remove editor -' + $(this).attr("type"));
    if ($(this).parents('.panel').hasClass('removed')) {
        $(this).parents('.panel').removeClass('removed');
        run_code( $('#test-mode[type=checkbox]').is(":checked"), btn_code_sumbit? btn_code_sumbit.hasClass('active') : null); 
        

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