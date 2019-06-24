var trackOutboundLink = function(inCategory) {
    debugger;
    if (gtag) {
        gtag('event', inCategory)
  }
}

$(document).ready(function() {

    var btn_watch= $("#btn-watch");

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
            <div class='editable-container' type='deadline'></div>
            <div class='editable-container' type='shortcut'></div>
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
            {2}
            <!-- add a shortcut editor button -->
            {3}`
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

        var tmp_simulate_load = false;
        // Load EditorRule - folder selection
        $("div[rule-id]").each(function() {
            var emailrule_id = $(this).attr('rule-id');

            var folders = [];
            for(var i=0; i < RULE_FOLDER.length ; i++) {
                if(RULE_FOLDER[i][1] == emailrule_id) {
                    $(this).find('.folder-container input[value="'+ RULE_FOLDER[i][0] + '"]').prop( "checked", true );
                    folders.push(RULE_FOLDER[i][0]);
                }
            }

            if(folders.length == 0) return;

            if($(this).parent().attr("type") == "new-message" && !tmp_simulate_load) {
                // TODO load only one when initialize 
                tmp_simulate_load = true;
                run_simulate_on_messages(folders, 5, this);
            }
                
        }) 

        var global_method = [];
        document.querySelectorAll('#apis-container div[property="folder"] h4').forEach(function(element) {
            global_method.push( $.trim(element.innerHTML.split("(")[0]) );
        });

        var entity_method = [];
        document.querySelectorAll('#apis-container div[property="message"] h4').forEach(function(element) {
            entity_method.push( $.trim(element.innerHTML.split("(")[0]) );
        });

        document.querySelectorAll('#apis-container div[property="contact"] h4').forEach(function(element) {
            entity_method.push( $.trim(element.innerHTML.split("(")[0]) );
        });

        document.querySelectorAll('#apis-container div[property="calendar"] h4').forEach(function(element) {
            entity_method.push( $.trim(element.innerHTML.split("(")[0]) );
        });

        CodeMirror.registerHelper('hint', 'dictionaryHint', function(editor) {
            var cur = editor.getCursor();
            var curLine = editor.getLine(cur.line);
            var start = cur.ch;
            var end = start;

            while (end < curLine.length && /[\w|\\.]/.test(curLine.charAt(end))) ++end;
            while (start && /[\w]/.test(curLine.charAt(start - 1))) --start;
            var curWord = start !== end && curLine.slice(start, end);
            var regex = new RegExp('^' + curWord, 'i');

            var suggestion = curLine.includes(".") ? 
                entity_method.filter(function(item) {
                    return item.match(regex);
                }).sort() : 
                global_method.filter(function(item) {
                    return item.match(regex);
                }).sort();

            if (curWord[curWord.length -1] == ".") suggestion = [];
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

    btn_watch.click(function (e) {
        watch_current_message(  ); 
    });

    $( "select[name='folder']" ).change(function() {
        console.log( $(this).find("option:selected").text() );
    });

    function show_loader( is_show ) {
        if(is_show) $(".sk-circle").show();
        else $(".sk-circle").hide();
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

    function watch_current_message() {
        var params = {};
        alert("")
        $.post('/watch_current_message', params,
            function(res) {
                console.log(res);
                
                if (res.status) {
                }
                else {
                    notify(res, false);
                }
            }
        ).fail(function(res) {
            alert("Please refresh the page!");
        });
    }

    show_loader(false);

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
