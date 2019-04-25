var trackOutboundLink = function(inCategory) {
    debugger;
    if (gtag) {
        gtag('event', inCategory)
  }
}

$(document).ready(function() {

    var user_name = $.trim($('#user_email').text()),
        btn_login = $("#btn-login"),
        btn_test_run = $("#btn-test-run"),
        btn_code_sumbit = $("#btn-code-submit"),
        btn_shortcut_save = $("#btn-shortcut-save");

    var log_backup = "", user_status_backup = "";
    var import_str = "import spacy"

    // Format string
    if (!String.prototype.format) {
        String.prototype.format = function() {
          var args = arguments;
          return this.replace(/{(\d+)}/g, function(match, number) { 
            return typeof args[number] != 'undefined'
              ? args[number]
              : match
            ;
          });
        };
    }

    function append_log( msg_log, is_error ) {
        if(!msg_log) return;

            // value = value.split("#!@log");
            var sorted = [];
            for(var key in msg_log) {
                sorted[sorted.length] = key;
            }
            sorted.sort();
            // sorted.reverse(); // 

            var t = $('#console-table').DataTable();
            $.each(sorted, function(index, timestamp) {                
                Message = msg_log[timestamp];
                _message_data = Message;
                // alert(Message["trigger"]);

                var json_panel_id = timestamp.replace(/[ /:,]/g,'');
                t.row.add( [
                        timestamp.split(",")[0],
                        '<span class="label label-info">{0}</span>'.format(Message["trigger"] || ""),
                        '<div class="jsonpanel contact" id="jsonpanel-from-{0}"></div>'.format(json_panel_id),
                        '<div class="jsonpanel" id="jsonpanel-{0}"></div>'.format(json_panel_id),
                        (Message["error"] ? '<span class="label label-danger">Error</span>' : "") + Message['log']
                ] ).draw( false );  

                // Delete attributes that are not allowed for users 
                delete Message["trigger"];
                delete Message["error"];
                delete Message["log"];
                delete Message["timestamp"];
                delete Message["type"];

                Contact :  Message['from_']
                $('#jsonpanel-from-' + json_panel_id).jsonpanel({
                    data: {
                        Contact :  Message['from_']
                    }
                });

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

            // $("#console-table").DataTable().row( $tableRow ).invalidate().draw();
            //     if(is_error) 
            //         $( "<p>" + datetime + log.replace(/\n/g , "<br>") + "</p>" ).appendTo( "#console-output" ).addClass("error");

            //     else $( log_table  ).prependTo( "#console-output" )
            //         .addClass("info");
            });

            // recent msg at top
            $("#console-table").DataTable().order([0, 'des']).draw();   

        // var datetime = format_date();
        // $( "<p>{0}</p>".format(datetime)).prependTo( "#console-output" ).addClass("info");
    }   

    function create_new_tab(nav_bar) {
        // Get ID of last tab and increment to avoid same ID
        var id_list = [];
        $("#editor-container .tab-pane").each(function(index,elem) {
            id_list.push(parseInt(elem.id.split("_")[1]))
        })
        var id = Math.max.apply(null, id_list) + 1;

        // Add tab
        $(nav_bar).closest('li').before('<li><a href="#tab_{0}"><span class="tab-title" mode-id={0}>In meeting <span>({0})</span></span><i class="fas fa-pencil-alt"></i></a> <span class="close"> x </span></li>'.format(id));

        // Insert tab pane first
        var tab_pane_content = `<div class='tab-pane' id='tab_{0}'> 
            <div class='editable-container' type='new-message'></div>
            <div class='editable-container' type='repeat'></div>
            <div class='editable-container' type='flag-change'></div>
        </div>`.format(id);
        $('.tab-content').append( tab_pane_content );

        // Move to the newly added tab to load style properly
        $('.nav-tabs li:nth-child(' + ($('.nav-tabs li').length-1) + ') a').click();

        // Add elements in the tab pane
        $('.tab-content').find('.tab-pane').last().append(
            `<!-- add a new message editor button -->
            {0}
            <!-- add a new flag-change editor button -->
            {1}
            <!-- add a deadline editor button -->
            {2}`
            .format(get_panel_elem("new-message", false), get_panel_elem("flag-change", false), get_panel_elem("deadline", false), get_panel_elem("shortcut", false)));

        unsaved_tabs.push( id );
    }

    function append_status_msg( msg, is_error ) {
        if(!msg) return;

        $.each( msg.split("\n"), function( key, value ) {
            value = $.trim(value);
            if(value == "") return;
            
            $( "<p>" + 
            '<span class="fa-layers fa-fw fa-2x"><i class="fas fa-sync"></i><span class="fa-layers-counter idle-mark" style="background:Tomato">IDLE</span></span>'
            + value.replace(/ *\[[^\]]*]/, '') + "</p>" ).prependTo( "#user-status-msg" )
            .addClass("info");

            spinStatusCog(true);
        });
        
    }

    function format_date() {
        var currentdate = new Date();
        var datetime = (currentdate.getMonth()+1) + "/"
            + currentdate.getDate() + "/" 
            + currentdate.getFullYear() + " @ "  
            + currentdate.getHours() + ":"  
            + currentdate.getMinutes() + ":" 
            + currentdate.getSeconds()
            + " | ";

        return datetime;
    }

    function makeMarker() {
        var marker = document.createElement("div");
        marker.style.color = "#822";
        marker.style.fontSize = "35px";
        marker.style.marginTop = "-15px";
        marker.style.fontWeight = "900";
        marker.innerHTML = "&rarr;";
        return marker;
      }

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

    function init_folder_selector($folder_container) {
        // nested tree checkboxs http://jsfiddle.net/rn290ywf/
        if (FOLDERS.length ==0)
            FOLDERS = ['INBOX', 'Family','Family/Sub folder1','Family/Sub folder2', 'Conference', 'Internship', 'Budget']
        
        // Init a new folder list

        // create folder nested structures
        folders_nested = {}
        $.each(FOLDERS, function(index, value) {
            if(value.includes("/")) {
                pwd = value.split("/")
                d = folders_nested
                $.each(pwd, function(i, v) {
                    if(v in d) {}
                    else { d[v] = {}
                    }
                    d = d[v]
                })
                folders_nested = $.extend(folders_nested,d)
            } else { 
                if( (value in folders_nested) == false)  
                    folders_nested[value]= {} 
                }        
        })

        function isDict(v) {
            return typeof v==='object' && v!==null && !(v instanceof Array) && !(v instanceof Date);
        }

        // dict => <ul><li>key1 <ul><li>key1-1</li></ul></li> <li>key2</li></ul>
        function rec_add_nested(d, path) {
            var $ul = $("<ul></ul>");
            for (var key in d) {
                var p = "";
                if (path=="") p = key;
                else  p = path + "/" + key;
                var $li;
                
                // if has children
                if( Object.keys(d[key]).length > 0 ) { 
                    $li = $("<li><input type='checkbox' value='"+ p + "' style='visibility:hidden;'>" + '<i class="far fa-folder-open"></i> ' + key + "</li>");
                    $li.append(rec_add_nested(d[key], p)) } 
                else {
                    $li = $("<li><input type='checkbox' value='"+ p + "'>" + '<i class="far fa-folder-open"></i> ' + key + "</li>");
                }

                $ul.append($li);
            }

            return $ul;
        }
        
        u = rec_add_nested(folders_nested, "")
        $folder_container.append(u)
    }

    function get_panel_elem(type, editable) {
        var func_name = ""
        switch(type) {
            case "new-message": 
                func_name="def on_message(my_message):";break;
            case "deadline": 
                func_name="def on_deadline(my_message):";break;
            case "flag-change": 
                func_name="def on_flag_added(my_message, added_flags):\n    pass\n\ndef on_flag_removed(my_message, removed_flags):";break;
            case "shortcut": 
                func_name="def on_command(my_message, content):";break;    
        }

        var instruction_for_shortcut = `<div class='instruction-container'><span>Forward your email to <b>run@youps.csail.mit.edu</b> with commands to trigger the shortcut!</span></div>`;

        var editor_elem = `<div class="panel-body" style="display:none;">` +
        (type=="shortcut"? instruction_for_shortcut: '<div class="folder-container"></div>') + 
        `<div class="editor-container">` +
            (type=="new-message"? `<div class='trigger'>
                <form class="form-inline">
                    <div class="form-group">
                        <span>When a message arrvies, run the following rules </span>
                    </div>
                    <div class="form-group">
                        <input class="form-check-input" type="radio" name="new-message-timespan" value="now" checked>
                        <label class="form-check-label" for="inlineRadio1">immediately</label>
                        <input class="form-check-input" type="radio" name="new-message-timespan" value="before">
                        <input style='width:50px;' type="text" class="form-control" placeholder="30">
                        <select id="company" class="form-control">
                            <option>min</option>
                            <option>hr</option>
                            <option>day</option>
                        </select> 													
                    </div>
                    <div class="form-group">
                        <span>later</span>
                    </div>
                </form></div>`:"") +
            `<textarea class="editor mode-editor">{0}\n{1}</textarea>
        </div>
        <div class='debugger-container' mv-app='editor2' mv-storage='#mv-data-container'  class='mv-autoedit' mv-mode='edit'>
            <button class='btn btn-default btn-debug-update'><i class="fas fa-sync"></i> Reload results</button>
            
            <h2>Test suites</h2>
            <h4>Recent messages from your selected folders to test your rules</h4>
            <table class="example-suites" class="row-border" style="width:100%">
            </table>
        </div>`
            .format(import_str, func_name + "\n    pass"), 
    pull_down_arrow = `<span class="pull-right">
        <button class='btn-default btn-incoming-save'>Save</button>
        <i class="fas fa-chevron-up" style="display:none;"></i><i class="fas fa-chevron-down"></i>
    </span>`;

        
        var elem_content;
        if(type == "new-message") {
            elem_content =  `{0}{1}<div {2} class="panel panel-success">
                <div class="flex_container">
                    <div class="flex_item_left"> 
                        <i class="fas fa-3x fa-{3}"></i>
                    </div>
                    
                    <div class="panel-heading flex_item_right panel-collapsed">
                        <h3 class="panel-title">
                            {4}
                        </h3>
                        {5}
                    </div>
                </div>
                <!-- Panel body -->
                {6}
            </div>`.format("", "",
                editable ? "rule-id={0}".format(Math.floor(Math.random() * 10000) + 1) : "",
                editable ? "trash" : "plus-circle",
                `<span style='float:left;' class="fa-layers fa-fw fa-2x"> 
                    <i class="far fa-envelope"></i>
                    <span class="fa-layers-counter" style="background:Tomato">NEW</span>
                </span>` + (editable ? `<input type="text" style="border: none;background: none;border-bottom: 2px solid;" placeholder="My email rule" /> 
                    <span class="preview-folder"></span>` : `Create message arrival handler <span class=""></span>`), 
                editable ? pull_down_arrow : "",
                editable ? editor_elem : "");
        } else if (type == "flag-change"){
            elem_content = `{0}{1}<div {2} class="panel panel-warning">
                <div class="flex_container">
                    <div class="flex_item_left"> 
                        <i class="fas fa-3x fa-{3}"></i>
                    </div>
                    
                    <div class="panel-heading flex_item_right panel-collapsed">
                        <h3 class="panel-title">
                            {4}
                        </h3>
                        {5}
                    </div>
                </div>
                <!-- Panel body -->
                {6}
            </div>
        </div>`.format("", "",
                editable ? "rule-id={0}".format(Math.floor(Math.random() * 10000) + 1) : "",
                editable ? "trash" : "plus-circle",
                '<i style="float:left;" class="far fa-2x fa-flag"></i>' + (editable ? `<input type="text" style="border: none;background: none;border-bottom: 2px solid;" placeholder="My email rule" /> 
                    <span class="preview-folder"></span>` : `Create a flag change event handler <span class=""></span>`), 
                editable ? pull_down_arrow : "",
                editable ? editor_elem : "");
        } else if (type == "deadline"){
            elem_content = `{0}{1}<div {2} class="panel panel-default">
                <div class="flex_container">
                    <div class="flex_item_left"> 
                        <i class="fas fa-3x fa-{3}"></i>
                    </div>
                    
                    <div class="panel-heading flex_item_right panel-collapsed">
                        <h3 class="panel-title">
                            {4}
                        </h3>
                        {5}
                    </div>
                </div>
                <!-- Panel body -->
                {6}
            </div>
        </div>`.format("", "",
                editable ? "rule-id={0}".format(Math.floor(Math.random() * 10000) + 1) : "",
                editable ? "trash" : "plus-circle",
                `<i style="float:left;" class="far fa-2x fa-clock"></i>` + (editable ? `<input type="text" style="border: none;background: none;border-bottom: 2px solid;" placeholder="My email rule" /> 
                    <span class="preview-folder"></span>` : `Create a deadline event handler <span class=""></span>`), 
                editable ? pull_down_arrow : "",
                editable ? editor_elem : "");
        } else if (type == "shortcut"){
            elem_content = `{0}{1}<div {2} class="panel panel-primary">
                <div class="flex_container">
                    <div class="flex_item_left"> 
                        <i class="fas fa-3x fa-{3}"></i>
                    </div>
                    
                    <div class="panel-heading flex_item_right panel-collapsed">
                        <h3 class="panel-title">
                            {4}
                        </h3>
                        {5}
                    </div>
                </div>
                <!-- Panel body -->
                {6}
            </div>
        </div>`.format("", "",
                editable ? "rule-id={0}".format(Math.floor(Math.random() * 10000) + 1) : "",
                editable ? "trash" : "plus-circle",
                `<i style="float:left;" class="fas fa-2x fa-terminal"></i>` + (editable ? `<input type="text" style="border: none;background: none;border-bottom: 2px solid;" placeholder="My email rule" /> 
                    <span class="preview-folder"></span>` : `Create a shortcut handler <span class=""></span>`), 
                editable ? pull_down_arrow : "",
                editable ? editor_elem : "");
        } else if (type == "repeat") {
            elem_content = `{0}{1}<div {2} class="panel panel-warning">
                <div class="flex_container">
                    <div class="flex_item_left"> 
                        <i class="fas fa-3x fa-{3}"></i> 
                    </div>
                    
                    <div class="panel-heading flex_item_right panel-collapsed">
                        <h3 class="panel-title">
                            <i class="far fa-2x fa-clock" style="float:left"></i>  
                            <span style="float:left;margin: 10px;">Update every </span>
                            <span class="preview-folder"></span>
                        </h3>
                        {5}
                    </div>
                </div>
                <!-- Panel body -->
                {4}
            </div>
        </div>`.format("", "",
                editable ? "rule-id={0}".format(Math.floor(Math.random() * 10000) + 1) : "",
                editable ? "trash" : "plus-circle",
                editable ? editor_elem : "",
                editable? pull_down_arrow : "");
        }

        if (!editable) 
            return '<div class="btn-new-editor" type="{0}">'.format(type) + elem_content + '</div>';
        return elem_content;
    }

    function guess_host( email_addr ) {
        $("#link-less-secure").attr('href', "");
        $("#rdo-oauth").attr('disabled', "");
        
        if( validateEmail(email_addr) ) {
            $("#password-container").show();
            toggle_login_mode();

            if( email_addr.includes("gmail")) {
                $("#input-host").val("imap.gmail.com");
                $("#link-less-secure").attr('href', "https://myaccount.google.com/lesssecureapps");
                $("#rdo-oauth").removeAttr('disabled');

                $(".oauth").show();
            }
            else {
                $(".oauth").remove();

                $("#rdo-plain").not(':checked').prop("checked", true);
                
                if ( email_addr.includes("yahoo")) $("#input-host").val("imap.mail.yahoo.com");
                else if ( email_addr.includes("csail")) $("#input-host").val("imap.csail.mit.edu");
                else if ( email_addr.includes("mit")) $("#input-host").val("imap.exchange.mit.edu");
                else $("#input-host").val("");

                $(".oauth").hide();
            }
        }
        else $("#password-container").hide();
    }

    // Disable all the buttons for a while until it is sure that the user is authenticated
    $(".btn").prop("disabled",true);
    
    var test_mode_msg = {true: "You are currently at test mode. YoUPS will simulate your rule but not actually run the rule.", 
        false: "YoUPS will apply your rules to your incoming emails. "};

    $("#mode-msg").text( test_mode_msg[is_test] );

    // for demo; set date to now
    $(".current-date").text(format_date());

    if(IS_RUNNING) {
        btn_code_sumbit.addClass('active')
    }

    

    /* Formatting function for row details - modify as you need */
    function format ( d ) {
        // `d` is the original data object for the row
        return '<table cellpadding="5" cellspacing="0" border="0" style="padding-left:50px;">'+
        'Debugging result here..'+
        '</table>';
    }

    var table = $('.example-suites').DataTable( {
        "bPaginate": false,
        "bLengthChange": false,
        "bFilter": true,
        "bInfo": false,
        "bAutoWidth": false,
        "searching": false,
        "columns": [
            { "width": "40px", "orderable": false },
            null,
            { "width": "300px" }
        ],
        // "columns": [
        //     {
        //         "className":      'details-control',
        //         "orderable":      false,
        //         "data":           null,
        //         "defaultContent": ''
        //     },
        //     { "data": "sender" },
        //     { "data": "subject" },
        //     { "data": "deadline" },
        //     { "data": "task" }
        // ],
        "order": [[1, 'asc']]
    } );

    var table = $('#console-table').DataTable( {
        "bPaginate": false,
        "bLengthChange": false,
        "bFilter": true,
        "bInfo": false,
        "bAutoWidth": false,
        "columnDefs": [
            { "type": "html-input", "targets": [2, 3] }
        ],
        "columns": [
            { "width": "40px" },
            { "orderable": false },
            { "width": "200px", "orderable": false },
            { "width": "400px", "orderable": false },
            { "orderable": false }
        ],
        "order": [[1, 'asc']],
        "drawCallback": function( settings ) {
            
        }
    } );

    var _message_data, _contact_data; // This global variable to pass around the row data
    $.fn.dataTableExt.ofnSearch['html-input'] = function(el) {
        // Fire after a row is drew
        return JSON.stringify(_message_data);
    };
    
    // Add event listener for opening and closing details
    $('.console-table tbody').on('click', 'td.details-control', function () {
        var tr = $(this).closest('tr');
        var row = table.row( tr );

        if ( row.child.isShown() ) {
            // This row is already open - close it
            row.child.hide();
            tr.removeClass('shown');
        }
        else {
            // Open this row
            row.child( format(row.data()) ).show();
            tr.addClass('shown');
        }
    } );

    // Create the sandbox:
    // window.sandbox = new Sandbox.View({
    //     el : $('#sandbox'),
    //     model : new Sandbox.Model()
    //   });

    // init editor  
    var unsaved_tabs = [];


    /**
     * Event listeners 
     * 
     */
    
    document.addEventListener("mv-load", function(e){   
        // Init editor & its autocomplete
        if(e.srcElement.id != "apis-container") return;

        // remember which tab should be active 
        var active_tab = $('.nav-tabs li.active');

        // Open individual tab and panel to load style properly
        $('.nav-tabs li').each(function() {
            if ( !$(this).find('span') || $(this).find('a').hasClass('add-tab') ) return;
            $(this).find('a').click();
					
			// At each tab
            $( $(this).find('a').attr('href') ).find('.panel').each(function() {
			    $(this).parents('.editable-container').find('.panel-heading').click();
                if ($(this).find('textarea').length) {
                    init_editor( $(this).find('textarea')[0] );
                }
                    
            })
            
        })

        // set dropdown to current mode name if exist
        if(current_mode) {
            active_tab.find('a').click();
            $(".dropdown .btn").html(current_mode + ' <span class="caret"></span>');
            $(".dropdown .btn").attr('mode-id', current_mode_id);
        }

        else {
            // init $("#current_mode_dropdown") with a default value if there is no selected mode yet
            var last_id = $('.nav.nav-tabs li.active').find('.tab-title').attr('mode-id');
            // var random_id = document.querySelector('.nav.nav-tabs li.active .tab-title').getAttribute('mode-id'),
            last_name = $.trim( document.querySelector('.nav.nav-tabs span[mode-id="'+ last_id + '"]').innerHTML );
            
            $(".dropdown .btn").html(last_name + ' <span class="caret"></span>');
            $(".dropdown .btn").attr('mode-id', last_id);
        }

        // Init folder container
        init_folder_selector( $(".folder-container") )

        // Load EditorRule - folder selection
        $("div[rule-id]").each(function() {
            var emailrule_id = $(this).attr('rule-id');

            for(var i=0; i < RULE_FOLDER.length ; i++) {
                if(RULE_FOLDER[i][1] == emailrule_id) {
                    $(this).find('.folder-container input[value="'+ RULE_FOLDER[i][0] + '"]').prop( "checked", true );
                    run_simulate_on_messages(RULE_FOLDER[i][0], 5, this);
                }
            }
        }) 

        var method_names = [];
        document.querySelectorAll('#apis-container h4').forEach(function(element) {
            method_names.push( element.innerHTML.split("(")[0] );
        });

        CodeMirror.registerHelper('hint', 'dictionaryHint', function(editor) {
            var cur = editor.getCursor();
            var curLine = editor.getLine(cur.line);
            var start = cur.ch;
            var end = start;

            while (end < curLine.length && /[\w$]/.test(curLine.charAt(end))) ++end;
            while (start && /[\w$]/.test(curLine.charAt(start - 1))) --start;
            var curWord = start !== end && curLine.slice(start, end);
            var regex = new RegExp('^' + curWord, 'i');

            var suggestion = method_names.filter(function(item) {
                return item.match(regex);
            }).sort();
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
    
    // Switch to different tabs
    $(".nav-tabs").on("click", "a", function (e) {
        e.preventDefault();

        if (!$(this).hasClass('add-tab')) {
            $(this).tab('show');
            // change to value of mode dropdown only if the engine is not currently running. 
            if(!btn_code_sumbit.hasClass('active')) {
                var last_id = $('.nav.nav-tabs li.active').find('.tab-title').attr('mode-id');
                last_name = $.trim( document.querySelector('.nav.nav-tabs span[mode-id="'+ last_id + '"]').innerHTML );

                $(".dropdown .btn").html(last_name + ' <span class="caret"></span>');
                $(".dropdown .btn").attr('mode-id', last_id);
            } 
        }
    })
    .on("click", "span.close", function () { // delete tab/mode
        var anchor = $(this).siblings('a');
        $(anchor.attr('href')).remove();
        $(this).parent().remove();
        $(".nav-tabs li").children('a').first().click();

        var mode_id = $(this).siblings('a').attr('href').split("_")[1];
        if( !unsaved_tabs.includes(mode_id) )
            delete_mode( mode_id );
    });

    $('.add-tab').click(function (e) {
        e.preventDefault();
        trackOutboundLink('addtab');

        create_new_tab(this);

        // Then save to DB.
        run_code( $('#test-mode[type=checkbox]').is(":checked"), btn_code_sumbit.hasClass('active') ); 
    });

    // add a new editor
    $("#editor-container").on("click", ".btn-new-editor", function() {
        trackOutboundLink('new editor -' + $(this).attr("type"));
        var $container = $( $(this).siblings("[type='{0}']".format($(this).attr("type"))) );
        var editor_elem = get_panel_elem($(this).attr("type"), true);
        $container.append( editor_elem );

        // open briefly to set styling
        $container.find(".panel-heading").last().click();
        init_editor( $container.find('textarea').last()[0] );
        debugger;
        $($container.find('.example-suites').last()[0]).DataTable( {
            "bPaginate": false,
            "bLengthChange": false,
            "bFilter": true,
            "bInfo": false,
            "bAutoWidth": false,
            "searching": false,
            "columns": [
                { "width": "40px", "orderable": false },
                null,
                { "width": "300px" }
            ],
            "order": [[1, 'asc']]
        } );
        $container.find(".panel-heading").last().click();

        

        init_folder_selector( $($container.find('.folder-container').last()[0]) );

        // check inbox folder by default
        $.each($($container.find('.folder-container').last()[0]).find("input"), function(index, elem) {
            if(elem.value.toLowerCase() == "inbox") {
                elem.checked = true;
                run_simulate_on_messages(elem.value, 5, $($container.find('div[rule-id]').last()[0]));
            }
        })
    });

    // remove / revive an editor
    $("#editor-container").on("click", ".editable-container .flex_item_left", function() {
        trackOutboundLink('remove editor -' + $(this).attr("type"));
        if ($(this).parents('.panel').hasClass('removed')) {
            $(this).parents('.panel').removeClass('removed');
            run_code( $('#test-mode[type=checkbox]').is(":checked"), btn_code_sumbit.hasClass('active') ); 

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

    // folder select listener
    $("#editor-container").on("change", ".folder-container input:checkbox", function() {
        var editor_rule_container = $(this).parents('div[rule-id]');

        if ($(this).is(':checked')) {
            run_simulate_on_messages($(this).val(), 5, editor_rule_container);
        }
        else { // remove from the table
                var dt_elem = $(this).parents('.panel-body').find('.debugger-container table')[0];
                dt = $( dt_elem ).DataTable();
                var folder_name = $(this).val();
                $.each($(dt_elem).find('tr[folder]'), function(index, elem) {
                    if(folder_name == $(elem).attr('folder'))
                        dt.row( elem ).remove().draw();
                })
        }

        // // Reload test results from the server
        // var msg_id = [];
        // $.each( $(this).parents('div[rule-id]').find(".debugger-container tr"), function(index, elem) {
        //     if($(elem).attr('msg-id'))
        //         msg_id.push( $(elem).attr('msg-id') )
            
        // })
    });

    // folder selector nested check
    $.extend($.expr[':'], {
        unchecked: function (obj) {
            return ((obj.type == 'checkbox' || obj.type == 'radio') && !$(obj).is(':checked'));
        }
    });

    $('#editor-container').on('change', '.folder-container input:checkbox', function() {
        // change children's value
        $(this).siblings('ul').find('input:checkbox').prop('checked', $(this).prop("checked"));

        for (var i = $('.folder-container').find('ul').length - 1; i >= 0; i--) {
            // find parents value
            $('.folder-container').find('ul:eq(' + i + ')').parents('li').find('> input').prop('checked', function () {
                return $(this).siblings('ul').find('input:unchecked').length === 0 ? true : false;
            });
        }
    });

    // debugging inspector
    $("#editor-container").on("click", ".debugger-container .detail-inspect", function() {
        trackOutboundLink('debug - detail');
        // $(this).attr("msg-id") // call simulate value
        $(this).parents("table").find("button").removeClass("detail-viewing");
        $(this).addClass("detail-viewing");
        
        // Remove line widgets
        $(".CodeMirror-linewidget").remove();

        var node = document.createElement('div')
        var display = document.createElement('div')
        
        node.appendChild(display)
        
        display.innerText = 'from: David Karger \nto: Amy Zhang, Soya Park, Luke Murray'// output
        display.style.backgroundColor = 'lightgray'
        display.style.padding = '5px'
        // node.style.height = '20px'

        $('body').find('.CodeMirror')[0].CodeMirror.addLineWidget(1, node)

        $('body').find('.CodeMirror')[0].CodeMirror.addLineWidget(1, node)

        const node2 = document.createElement('div')
        var display = document.createElement('div')
        
        node2.appendChild(display)
        
        display.innerText = 'flags: [] -> ["should read"]'// output
        display.style.backgroundColor = 'lightyellow'
        display.style.padding = '5px'
        
        $('body').find('.CodeMirror')[0].CodeMirror.addLineWidget(2, node2)
    }); 

    // run simulation on the editor
    $("#editor-container").on("click", ".btn-debug-update", function() {
        trackOutboundLink('run simulate');
        var editor_rule_container = $(this).parents('div[rule-id]');
        debugger;

        run_simulate_on_messages($(editor_rule_container).find('.folder-container input:checked').val(), 5, editor_rule_container);
    }); 

    // Tab name editor
    var editHandler = function() {
      var t = $(this);
      t.css("visibility", "hidden");
      $(this).siblings('.tab-title').attr("contenteditable", "true").focusout(function() {
        $(this).removeAttr("contenteditable").off("focusout");
        t.css("visibility", "visible");
      });
    };
    
    $( "body" ).on( "click", ".nav-tabs .fa-pencil-alt", editHandler);

    // Reload dropdown menu
    $("#current_mode_dropdown").on("click", function() {
        var $ul = $(this).parents(".dropdown").find('.dropdown-menu');
        $ul.empty();

        var modes = get_modes();
        $.each( modes, function( key, value ) {
            $ul.append( '<li><a href="#" data-value="action" mode-id='+ value.id + '>' + value.name + '</a></li>' );
        });
    });


    // change mode by dropdown click
    $("body").on("click", ".dropdown li a", function() {
        $(this).parents(".dropdown").find('.btn').html($(this).text() + ' <span class="caret"></span>');
        $(this).parents(".dropdown").find('.btn').attr('mode-id', $(this).attr('mode-id'));
        $(this).parents(".dropdown").find('.btn').val($(this).data('value'));

        // update current_mode
        is_success = run_code( $('#test-mode[type=checkbox]').is(":checked"), $(this).hasClass('active'));
        if(!is_success) {
            btn_code_sumbit.removeClass('active');
        }
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

    // $("#password-container").hide();
    guess_host($("#user-full-email").text());
    toggle_login_mode();

    if(is_imap_authenticated) {
        fetch_log(); 

        $(".btn").prop("disabled",false);
    }
    
	$('input[type=radio][name=auth-mode]').change(function() {
        toggle_login_mode();      
    });

    $("#test-mode[type=checkbox]").switchButton({
        labels_placement: "right",
        on_label: 'Test mode',
        off_label: '',
        checked: is_test
    });

    btn_code_sumbit.click(function() {   
        is_success = run_code( $('#test-mode[type=checkbox]').is(":checked"), !$(this).hasClass('active') );

        if(is_success) {
            // $(this).toggleClass('active');  
            
            if ($(this).find('.btn-primary').size()>0) {
                $(this).find('.btn').toggleClass('btn-primary');
            }
            $(this).find('.btn').toggleClass('btn-default');
        } else {// turn off the button
            // this is a hack, but after this click handler, the active class will be toggled. add active class so that it will be removed   
            $(this).addClass('active');  

            if ($(this).find('.btn-primary').size()>0) {
                $(this).find('.btn').removeClass('btn-primary');
            }
            $(this).find('.btn').addClass('btn-default');
        }
        
    });

    $("body").on("click", ".btn-incoming-save", function() {
        // save the code to DB
        run_code( $('#test-mode[type=checkbox]').is(":checked"), btn_code_sumbit.hasClass('active') ); 
    })

    btn_shortcut_save.click(function() {
        save_shortcut();
    })

    $('#test-mode[type=checkbox]').change(function() {
        var want_test = $(this).is(":checked");
        $("#mode-msg").text( test_mode_msg[ want_test ] );
        if(get_running())
            run_code( want_test, true ); 
    });

    function delete_mode( id_to_delete ) {
        var params = {
            'id': id_to_delete
        };

        $.post('/delete_mailbot_mode', params,
            function(res) {
                // $('#donotsend-msg').hide();
                console.log(res);
                
                // Delete success
                if (res.status) {
                    if( id_to_delete == get_current_mode()['id'] ) {
                        set_running(false);
                        $(".dropdown .btn").html("Select your mode" + ' <span class="caret"></span>');
                    }
                        
                }
                else {
                    notify(res, false);
                }
            }
        );
    }

    function show_loader( is_show ) {
        if(is_show) $(".sk-circle").show();
        else $(".sk-circle").hide();
    }
	
	function toggle_login_mode() {
		oauth = $('#rdo-oauth').is(":checked");
		if (oauth) {
            $(".oauth").show();
            $(".plain").hide();
		} else {
			$(".oauth").hide();
            $(".plain").show();
		}
    }

    function get_current_mode() {
        var id = $("#current_mode_dropdown").attr('mode-id'),
            code = document.querySelector('#tab_'+ id +' .CodeMirror').CodeMirror.getValue();

        return {"id": id,
            "name": $.trim(document.querySelector('.nav.nav-tabs li.active .tab-title').innerHTML), 
            "code": code
        };
    }

    function get_modes() {
        var modes = {};

        // iterate by modes 
        $("#editor-container .tab-pane").each(function() {
            var editors = [];

            // get mode ID
            var id = $(this).attr('id').split("_")[1];
            var name = $.trim( $(".nav.nav-tabs span[mode-id='{0}'].tab-title".format(id)).html() ).split("<span")[0]

            // iterate by editor 
            $(this).find('.CodeMirror').each( function(index, elem) {
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

                editors.push({"uid": uid, "name": name, "code": $.trim( code ).replace('\t', "    "), "type": type, "folders": selected_folders}); 
            })

            modes[id] = {
                "id": id,
                "name": $.trim( name ), 
                "editors": editors
            };
        })

        return modes;
    }

    function get_running() {
        return is_running;
    }

    function set_running(start_running) {
        // Start running
        if(start_running) {
            spinStatusCog(true);
            $("#engine-status-msg").text("Your email engine is running.");
            is_running = true;
        }
        
        // Stop running
        else {
            spinStatusCog(false);
            $("#engine-status-msg").text("Your email engine is not running at the moment.");
            is_running = false;
        }
    }
    
    function spinStatusCog(spin) {
        if(spin) {
            if( fa_sync = document.querySelector(".fa-sync"))
                fa_sync.classList.add("fa-spin");
            if( idle_mark = document.querySelector(".idle-mark"))
                idle_mark.style.display = "none";
        }
        else {
            if( fa_sync = document.querySelector(".fa-sync"))
                fa_sync.classList.remove("fa-spin");
            if( idle_mark = document.querySelector(".idle-mark"))   
                idle_mark.style.display = "inline-block";
        }
    }

    function fetch_log() {
        var params = {};
        
        $.post('/fetch_execution_log', params,
            function(res) {
                // $('#donotsend-msg').hide();
                // console.log(res);
                
                // Auth success
                if (res.status) {
                    // Update execution log
                    if( log_backup != res['imap_log']){
                        msg_log = JSON.parse(res['imap_log']);

                        // if it's a first time loading the log, display only recent 10 messages then enalbe 'load more' btn.
                        if(log_backup == '') {
                            var recent_keys = Object.keys(msg_log).sort(function(a, b) {return a>b;}).slice(-10);
                            append_log( recent_keys.reduce(function(o, k) { o[k] = msg_log[k]; return o; }, {}) );
                            
                            var initial_msg_log = msg_log;
                            $("#btn-log-load-more").show().click(function() {
                                var rest_key = $(Object.keys(initial_msg_log)).not(recent_keys).get();
                                append_log(rest_key.reduce((a, c) => ({ ...a, [c]: initial_msg_log[c] }), {}), false);
                                $(this).hide();
                            });
                        }

                        else {
                            old_log = JSON.parse(log_backup == '' ? '{}':log_backup)

                            // append new logs from the server
                            var new_msg_key = $(Object.keys(msg_log)).not(Object.keys(old_log)).get();
                            
                            append_log(new_msg_key.reduce((a, c) => ({ ...a, [c]: msg_log[c] }), {}), false);
                        }
                            //replace(/: True/g, ': true').replace(/: False/g, ': false').replace(/\'/g, '"').replace(/\</g, '&lt;').replace(/\>/g, '&gt;'));
                        // msg_log = JSON.parse(res['imap_log'].replace(/: True/g, ': true').replace(/: False/g, ': false').replace(/\'/g, '"').replace(/\</g, '&lt;').replace(/\>/g, '&gt;'));
                        

                        
                    }
                    
                    log_backup = res['imap_log'];

                    // if status_msg exists, it means a code is running 
                    if( $.trim( res['user_status_msg'] ) != "")
                        set_running(true)
                    else set_running(false)

                    // Update status msg
                    if( user_status_backup != res['user_status_msg']){
                        $("#user-status-msg").html("");
                        append_status_msg(res['user_status_msg'], false);
                    }
                    
                    user_status_backup = res['user_status_msg'];
                }
                else {
                    notify(res, false);
                }
            }
        ).fail(function(res) {
            alert("Please refresh the page!");
        });
        
        setTimeout(fetch_log, 2 * 1000); // 2 second
    }

    function validateEmail(email) {
        var re = /^(([^<>()\[\]\\.,;:\s@"]+(\.[^<>()\[\]\\.,;:\s@"]+)*)|(".+"))@((\[[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\])|(([a-zA-Z\-0-9]+\.)+[a-zA-Z]{2,}))$/;
        return re.test(String(email).toLowerCase());
    }    

        // When user first try to login to their imap. 
        btn_login.click(function() {
                show_loader(true);

                var params = {
                    'host': $("#input-host").val(),
                    'password': $('#rdo-oauth').is(":checked") ? $("#input-access-code").val() : $("#input-password").val(),
                    'is_oauth': $('#rdo-oauth').is(":checked")
                };
        
                $.post('/login_imap', params,
                    function(res) {
                        show_loader(false);
                        // $('#donotsend-msg').hide();
                        console.log(res);
                        
                        // Auth success
                        if (res.status) {
                            // Show coding interfaces 
                            $("#login-email-form").hide();
                            $(".btn").prop("disabled",false);

                            if ('imap_code' in res) {
                                editor.setValue( res['imap_code'] );
                                spinStatusCog(true);
                            }
                            
                            append_log(res['imap_log'], false)
                            
                            if (res.code) { 
                            }
                            else {                        
                                notify(res, true);
                            }

                            // then ask user to wait until YoUPS intialize their inbox
                            show_loader(true);
                            $("#loading-wall").show();
                            $("#loading-wall span").show();
                        }
                        else {
                            notify(res, false);
                        }
                    }
                ).fail(function(res) {
                    alert("Fail to load! Can you try using a different browser? 403");
                });    
        });

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

        function run_code(is_dry_run, is_running) {
            var cur_mode;
            try {
                cur_mode = get_current_mode();
            } catch (err){
                notify({'code': 'There is no rule defined in this mode'}, false);
                return false;
            }

            show_loader(true);

            var modes = get_modes();

            var params = {
                'current_mode_id': cur_mode['id'],
                'modes': JSON.stringify(modes),
                'email': $("#input-email").val(),
                'test_run': is_dry_run,
                'run_request': is_running
            };

            $.post('/run_mailbot', params,
                function(res) {
                    show_loader(false);
                    console.log(res);
                    
                    // Auth success
                    if (res.status) {
                        
                        // Flush unsaved tags 
                        unsaved_tabs = [];

                        if(res['imap_error'])  {
                            append_log(res['imap_log'], true);

                            set_running(false);   
                        }
                        else {
                            // append_log(res['imap_log'], false)

                            set_running(is_running);   
                        }

                        if (res.code) { 
                            // some emails are not added since they are not members of the group
                            // $('#donotsend-msg').show();
                            // $('#donotsend-msg').html(res['code']);
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

            return true;
        }

        // function folder_recent_messages(folder_name, N, code="") {
        //     var params = {
                
        //     };
            
        //     $.post('/folder_recent_messages', params,
        //         function(res) {
        //             // Load messages successfully 
        //             if (res.status) {
        //                 var t = $('#example').DataTable();
    
        //                 $.each( res['messages'], function( msg_id, value ) {
        //                     var Message = value;
    
        //                     var json_panel_id = Math.floor(Math.random() * 10000) + 1;
    
        //                     var added_row = t.row.add( [
        //                         '<div class="jsonpanel contact" id="jsonpanel-from-{0}"></div>'.format(json_panel_id),
        //                         '<div class="jsonpanel" id="jsonpanel-{0}"></div>'.format(json_panel_id),
        //                         'No action  <button msg-id={0} class="detail-inspect">detail</button>'.format(msg_id)
        //                     ] ).draw( false ).node();
        //                     $( added_row ).attr('folder', Message['folder'])
        //                         .attr('msg-id', msg_id);
    
        //                     $('#jsonpanel-from-' + json_panel_id).jsonpanel({
        //                         data: {
        //                             Contact :  Message['from_'] || []
        //                         }
        //                     });
            
        //                     // set contact object preview 
        //                     // $('#jsonpanel-from-' + json_panel_id + " .val-inner").text(
        //                     //     '"{0}", '.format(Message['from_']['name']) + '"{0}", '.format(Message['from_']['email'])  + '"{0}", '.format(Message['from_']['organization'])  + '"{0}", '.format(Message['from_']['geolocation'])  );
            
                            
        //                     $('#jsonpanel-' + json_panel_id).jsonpanel({
        //                         data: {
        //                             Message : Message
        //                         }
        //                     });
            
        //                     // set msg object preview 
        //                     var preview_msg = '{0}: "{1}", '.format("subject", Message['subject']) +  '{0}: "{1}", '.format("folder", Message['folder']);
        //                     for (var key in Message) {
        //                         if (Message.hasOwnProperty(key)) {
        //                             preview_msg += '{0}: "{1}", '.format(key, Message[key])
        //                         }
        //                     }
        //                     $("#jsonpanel-" + json_panel_id + " .val-inner").text( preview_msg );
        //                   });
                        
        //                   if(code)
        //                       run_simulate_on_messages(code, Object.keys(res['messages']));
        //             }
        //             else {
        //                 notify(res, false);
        //             }
        //         }
        //     );
        // }

        function run_simulate_on_messages(folder_name, N, editor_rule_container) {
            show_loader(true);
            

            var params = {
                'folder_name': folder_name,
                'N': N,
                'user_code': $.trim( $(editor_rule_container).find('.CodeMirror')[0].CodeMirror.getValue() )
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
                        $.each($(dt_elem).find('tr[folder]'.format(folder_name)), function(index, elem) {
                            if(folder_name == $(elem).attr('folder'))
                                t.row( elem ).remove().draw();  
                        })

                        $.each( res['messages'], function( msg_id, value ) {
                            var Message = value;
    
                            var json_panel_id = Math.floor(Math.random() * 10000) + 1;
    
                            var added_row = t.row.add( [
                                '<div class="jsonpanel contact" id="jsonpanel-from-{0}"></div>'.format(json_panel_id),
                                '<div class="jsonpanel" id="jsonpanel-{0}"></div>'.format(json_panel_id),
                                '{0}'.format(Message["log"].replace(/\n/g , "<br>"))
                                // '{1}  <button msg-id={0} class="detail-inspect"></button>'.format(msg_id, Message["log"])
                            ] ).draw( false ).node();
                            

                            $( added_row ).attr('folder', Message['folder'])
                                .attr('msg-id', msg_id)
                                .attr('line-number2', 1);
                                
                                // .attr('line-number{0}', 1); // TODO add activated line
                            if(Message["error"] == "True")
                                $( added_row ).find("td:eq(2)").addClass("error");
                            // else $( added_row ).find("td:eq(2)").addClass(json_panel_id % 2 == 0? "warning":""); 
                            if(json_panel_id % 2 == 0) $( added_row ).attr('line-number3', 1);     

                            // Delete attributes that are not allowed for users 
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
                    run_code( $('#test-mode[type=checkbox]').is(":checked"), btn_code_sumbit.hasClass('active') ); 
                }
            );
        }

        function save_shortcut() {
            show_loader(true);

            var params = {
                'shortcuts' : document.querySelector('#editor-shortcut-container .CodeMirror').CodeMirror.getValue()
            };

            $.post('/save_shortcut', params,
                function(res) {
                    show_loader(false);
                    console.log(res);
                    
                    // Auth success
                    if (res.status) {

                        if (res.code) { 
                            // some emails are not added since they are not members of the group
                            // $('#donotsend-msg').show();
                            // $('#donotsend-msg').html(res['code']);
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
    
        $(".default-text").blur();

        tinyMCE.init({
            mode: "textareas",
            theme: "advanced",
            theme_advanced_buttons1: "bold,italic,underline,strikethrough,|,justifyleft,justifycenter,justifyright,justifyfull,|,blockquote",
            theme_advanced_toolbar_location: "top",
            theme_advanced_toolbar_align: "left",
            theme_advanced_statusbar_location: "bottom",
            theme_advanced_resizing: true
        });
    });
