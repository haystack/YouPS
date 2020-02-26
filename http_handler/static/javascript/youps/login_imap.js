var trackOutboundLink = function(inCategory) {
    if (gtag) {
        gtag('event', inCategory)
  }
}

$(document).ready(function() {

    var user_email = $.trim($('#user_email').text()),
        btn_login = $("#btn-login"),
        btn_test_run = $("#btn-test-run"),
        btn_code_sumbit = $("#btn-code-submit"),
        btn_shortcut_save = $("#btn-shortcut-save");

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

    var test_mode_msg = {true: "You are currently at test mode. YouPS will simulate your rule but not actually run the rule.", 
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

        if( !$.isEmptyObject(get_modes()) )
            // Go to first tab if current one is deleted 
            $(".nav-tabs li").children('a').first().click();

        var mode_id = $(this).siblings('a').attr('href').split("_")[1];
        if( !unsaved_tabs.includes(mode_id) )
            delete_mode( mode_id );
    });

    $('.add-tab').click(function (e) {
        e.preventDefault();
        trackOutboundLink('addtab');

        create_mode(this);

        // Then save to DB.
        run_code( $('#test-mode[type=checkbox]').is(":checked"), btn_code_sumbit.hasClass('active') ); 
    });

    // folder select listener
    $("#editor-container").on("change", ".folder-container input:checkbox", function() {
        var editor_rule_container = $(this).parents('div[rule-id]');

        if ($(this).is(':checked')) {
            run_simulate_on_messages([$(this).val()], 5, editor_rule_container);
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

        var folders = [];
        $.each($(editor_rule_container).find('.folder-container input:checked'), function(index, val) {
            folders.push($(this).val())
        })
        run_simulate_on_messages(folders, 5, editor_rule_container);
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
    $("body").on("click", "#mode-selection-dropdown li a", function() {
        $(this).parents(".dropdown").find('.btn').html($(this).text() + ' <span class="caret"></span>');
        $(this).parents(".dropdown").find('.btn').attr('mode-id', $(this).attr('mode-id'));
        $(this).parents(".dropdown").find('.btn').val($(this).data('value'));

        // update current_mode
        is_success = run_code( $('#test-mode[type=checkbox]').is(":checked"), $(this).hasClass('active'));
        if(!is_success) {
            btn_code_sumbit.removeClass('active');
        }
    })

    $("body").on("click", ".btn-incoming-save", function() {
        // save the code to DB
        run_code( $('#test-mode[type=checkbox]').is(":checked"), btn_code_sumbit.hasClass('active') ); 
    })

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

    // $("#password-container").hide();
    guess_host(user_email);
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

    $("#btn-google-access").click(function() {

        
        window.open('https://accounts.google.com/o/oauth2/auth?client_id=1035128514395-ljeutpptbag8unpv2lgo1k93eiq006f6.apps.googleusercontent.com&redirect_uri=urn%3Aietf%3Awg%3Aoauth%3A2.0%3Aoob&response_type=code&scope=https%3A%2F%2Fmail.google.com%2F&login_hint='
            + user_email);
    })

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

    // Ctrl-s or Command-s
    $(window).keypress(function(event) {
        if (!(event.which == 115 && (event.metaKey || event.ctrlKey)) && !(event.which == 19)) return true;
        event.preventDefault();
        run_code( $('#test-mode[type=checkbox]').is(":checked"), btn_code_sumbit.hasClass('active') ); 
        return false;
    });


    $('#test-mode[type=checkbox]').change(function() {
        var want_test = $(this).is(":checked");
        $("#mode-msg").text( test_mode_msg[ want_test ] );
        if(get_running())
            run_code( want_test, true ); 
    });

    function create_mode( nav_bar ) {
        var params = {};

        $.post('/create_mailbot_mode', params,
            function(res) {
                console.log(res);
                
                // Create success
                if (res.status) {
                    var id = res["mode-id"]

                    // Add tab
                    $(nav_bar).closest('li').before('<li><a href="#tab_{0}"><span class="tab-title" mode-id={0}>My email mode <span>({0})</span></span><i class="fas fa-pencil-alt"></i></a> <span class="close"> x </span></li>'.format(id));

                    // // Insert tab pane first
                    // var tab_pane_content = `<div class='tab-pane' id='tab_{0}'> 
                    //     <div class='editable-container' type='new-message'></div>
                    //     <div class='editable-container' type='repeat'></div>
                    //     <div class='editable-container' type='flag-change'></div>
                    //     <div class='editable-container' type='deadline'></div>
                    //     <div class='editable-container' type='shortcut'></div>
                    // </div>`.format(id);
                    // $('.tab-content').append( tab_pane_content );

                    // Add elements in the tab pane
                    $('.tab-content').append(res['new_mode']);

                    // Move to the newly added tab to load style properly
                    $('.nav-tabs li:nth-child(' + ($('.nav-tabs li').length-1) + ') a').click();

                    
                        
                }
                else {
                    notify(res, false);
                }
            }
        );
    }

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

    

    function watch_current_message() {
        var params = {};
        
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


    function validateEmail(email) {
        var re = /^(([^<>()\[\]\\.,;:\s@"]+(\.[^<>()\[\]\\.,;:\s@"]+)*)|(".+"))@((\[[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\])|(([a-zA-Z\-0-9]+\.)+[a-zA-Z]{2,}))$/;
        return re.test(String(email).toLowerCase());
    }    

        // When user first try to login to their imap. 
        btn_login.click(function() {
                show_loader(true);
                $("#loading-wall").show();
                $("#loading-wall span").show();

                var params = {
                    'host': $("#input-host").val(),
                    'username': $("#input-username").val(),
                    'password': CryptoJS.AES.encrypt($('#rdo-oauth').is(":checked") ? $("#input-access-code").val() : $("#input-password").val(), "yYjdthJ6Hg0PAreSMqKq").toString(),
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
                            
                        }
                        else {
                            $("#loading-wall").hide();
                            notify(res, false);
                        }
                    }
                ).fail(function(res) {
                    alert("Fail to load! Can you try using a different browser? 403");
                });    
        });

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
    
        $(".default-text").blur();
        
        // 
        load_rule(true);

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

    function get_current_mode() {
        var id = $("#current_mode_dropdown").attr('mode-id');

        return {"id": id,
            "name": $.trim(document.querySelector('.nav.nav-tabs li.active .tab-title').innerHTML)
        };
    }

    function get_modes() {
        var modes = {};

        // iterate by modes 
        $("#editor-container .tab-pane").each(function() {
            // get mode ID
            if(!$(this).attr('id').includes("_")) return;
            var id = $(this).attr('id').split("_")[1];
            var name = $.trim( $(".nav.nav-tabs span[mode-id='{0}'].tab-title".format(id)).html() ).split("<span")[0]

            // iterate by editor 
            var editors = extract_rule_code(this)

            modes[id] = {
                "id": id,
                "name": $.trim( name ), 
                "editors": editors
            };
        })

        return modes;
    }

    // if load_exist true, it bulk loads all the message. Otherwise loads only one editor
    function load_rule(load_exist, rule_type=null, $container=null) {
        show_loader(true);

        var params = {
            'load_exist' : load_exist,
            'type': rule_type
        };

        if (!load_exist) params['mode'] = get_current_mode()['id'];

        $.post('/load_new_editor', params,
        function(res) {
            show_loader(false);
            console.log(res);
            
            if (res.status) {
                if (res.code) { 
                    if (load_exist) {
                        // TODO devide the part attach and retrieve components 
                        $.each(res.editors, function( index, value ) {
                            $( "#tab_{0} .editable-container[type='{1}']".format(value['mode_uid'], value['type']) ).append(value['template']);
                        });
                        
                        var active_tab = $('.nav-tabs li.active');
                        
                        // Open individual tab and panel to load style properly
                        $('.nav-tabs li').each(function() {
                            if ( !$(this).find('span') || $(this).find('a').hasClass('add-tab') ) return;
                        
                            // open this tab
                            $(this).find('a').click();
                                
                            // open all the editors
                            // NOTE: weird bootstrap bug, it only opens if following lines are here. It doesn't work with only either one
                            $( $(this).find('a').attr('href') ).find('.editable-container .panel-heading').click();
                            $( $(this).find('a').attr('href') ).find('.editable-container .panel-heading').each(function() {
                                $(this).click();
                            })
    
                            $( $(this).find('a').attr('href') ).find('.editable-container textarea.editor').each(function() {
                                init_editor( this );
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
                        
                        $('.example-suites').DataTable( {
                            "bPaginate": false,
                            "bLengthChange": false,
                            "bFilter": true,
                            "bInfo": false,
                            "bAutoWidth": false,
                            "searching": false,
                            "language": {
                                "emptyTable": 'Click "Debug my code" to test your rule',
                                "infoEmpty": "No entries to show",
                                "zeroRecords": "No records to display"
                              },
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
                    } 

                    else {
                        $container.append( res.editors[0]['template'] );
                        
                        // open briefly to set styling
                        $container.find(".panel-heading").last().click();
                        $container.find(".panel-heading").last().click();
                                init_editor( $container.find('textarea').last()[0] );
        
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
                                    "language": {
                                        "emptyTable": 'Click "Debug my code" to test your rule',
                                        "infoEmpty": "No entries to show",
                                        "zeroRecords": "No records to display"
                                      },
                                    "order": [[1, 'asc']]
                                } );
                        
                                
                        
                                // init_folder_selector( $($container.find('.folder-container').last()[0]) );
                        
                                // check inbox folder by default
                                // $.each($($container.find('.folder-container').last()[0]).find("input"), function(index, elem) {
                                //     if(elem.value.toLowerCase() == "inbox") {
                                //         elem.checked = true;
                                //         if($(this).attr("type") == "new-message")
                                //             run_simulate_on_messages([elem.value], 5, $($container.find('div[rule-id]').last()[0]));
                                //     }
                                // })
                    }
                }
                else {                        
                    notify(res, true);
                }
            }
            else {
                notify(res, false);
            }
        }
    );}

    function get_running() {
        return is_running;
    }

    function set_running(start_running) {
        // Start running
        if(start_running) {
            is_running = true;
        }
        
        // Stop running
    else {
            is_running = false;
        }
    }

    function run_code(is_dry_run, is_running, silent=false) {
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
            'current_mode_id': 'id' in cur_mode? cur_mode['id']: null,
            'modes': JSON.stringify(modes),
            'email': $("#input-email").val(),
            'test_run': is_dry_run,
            'run_request': is_running
        };

        $.post('/run_mailbot', params,
            function(res) {
                show_loader(false);
                console.log(res);
                
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
                        if(!silent)             
                            notify(res, true);
                    }
                }
                else {
                    set_running(false);   
                    notify(res, false);
                }
            }
        );

        return true;
    }