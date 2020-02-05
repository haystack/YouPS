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

    

    // run simulation on the editor
    $("#editor-container").on("click", ".btn-debug-update", function() {
        trackOutboundLink('run simulate');
        var editor_rule_container = $(this).parents('div[rule-id]');

        var folders = [];
        $.each($(editor_rule_container).find('.folder-container input:checked'), function(index, val) {
            folders.push($(this).val())
        })
        run_simulate_on_messages(folders, 5, editor_rule_container);
    }); 

    $("body").on("click", ".btn-incoming-save", function() {
        // save the code to DB
        save_rules( ); 
    })
	

    function run_simulate_on_messages(editor_rule_container) {
        show_loader(true);
    
        var params = {
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
                    $.each($(dt_elem).find('tr[folder]'), function(index, elem) {
                        if(folder_name.includes($(elem).attr('folder')))
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
                        if(Message["error"])
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
                run_code( $('#test-mode[type=checkbox]').is(":checked"), btn_code_sumbit.hasClass('active'), true ); 
            }
        );
    }
   
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


// if load_exist true, it bulk loads all the message. Otherwise loads only one editor
function load_rule(load_exist, rule_type=null, $container=null) {
    show_loader(true);

    var params = {
        'load_exist' : load_exist,
        'type': 'shortcut'
    };

    $.post('/load_new_editor', params,
    function(res) {
        show_loader(false);
        console.log(res);
        
        if (res.status) {
            if (res.code) { 
                if (load_exist) {
                    // TODO devide the part attach and retrieve components 
                    $.each(res.editors, function( index, value ) {
                        $( ".editable-container[type='shortcut']").append(value['template']);
                    });

                    $('.editable-container textarea.editor').each(function() {
                        init_editor( this );
                    })

                    $( ".editable-container[type='shortcut'] .panel-heading").click();
                    
                    // Init folder container
                    // init_folder_selector( $(".folder-container") )
                    
                    // var tmp_simulate_load = false;
                    // // Load EditorRule - folder selection
                    // $("div[rule-id]").each(function() {
                    //     var emailrule_id = $(this).attr('rule-id');
                    
                    //     var folders = [];
                    //     for(var i=0; i < RULE_FOLDER.length ; i++) {
                    //         if(RULE_FOLDER[i][1] == emailrule_id) {
                    //             $(this).find('.folder-container input[value="'+ RULE_FOLDER[i][0] + '"]').prop( "checked", true );
                    //             folders.push(RULE_FOLDER[i][0]);
                    //         }
                    //     }
                    
                    //     if(folders.length == 0) return;
                    
                    //     if($(this).parent().attr("type") == "new-message" && !tmp_simulate_load) {
                    //         // TODO load only one when initialize 
                    //         tmp_simulate_load = true;
                    //         run_simulate_on_messages(folders, 5, this);
                    //     }
                            
                    // }) 
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

var btn_code_sumbit = null;

function run_code() {
    save_rules();
}

function save_rules() {
    var editors = extract_rule_code(document.getElementById("editor-container"));

    var params = {
        'rules': JSON.stringify(editors)
    };

    $.post('/save_rules', params,
        function(res) {
            show_loader(false);
            console.log(res);
            
            if (res.status) {
                
                notify(res, true);
            }
            else {
                set_running(false);   
                notify(res, false);
            }
        }
    );

}