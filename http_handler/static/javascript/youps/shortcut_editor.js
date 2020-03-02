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

        run_simulate_on_messages(["INBOX"], 3, editor_rule_container, extract_shortcut_argument($(this).parents(".panel-body")), debugging_messages_ids);
    }); 

    $("body").on("click", ".btn-incoming-save", function() {
        // save the code to DB
        save_rules( ); 
    })
	
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
                    
                    $('.example-suites').DataTable(datatable_config );
                } 

                else {
                    $container.append( res.editors[0]['template'] );
                    
                    // open briefly to set styling
                    $container.find(".panel-heading").last().click();
                    $container.find(".panel-heading").last().click();
                            init_editor( $container.find('textarea').last()[0] );
    
                            $($container.find('.example-suites').last()[0]).DataTable( datatable_config );
                    
                            
                    
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