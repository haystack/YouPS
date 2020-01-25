const  buttonService  =  new ButtonService();
var watched_message = [];
function fetch_watch_message() {
  var params = {
      "watched_message": watched_message
  };
  
  $.post('/fetch_watch_message', params,
      function(res) {
        console.log(res);
        console.log(res["message_row"]);

          if (res.status) {
              if ( !res['watch_status'] ) {
                  spin_watch_btn(false);
                  return;
              }

              if(res["log"]) { // something went wrong
                  watching_msg_container.find("span").text("");
                  watching_msg_container.find("[name='subject']").text( res["log"] );
              }
              // TODO if the message is from a different folder, noop 
              // uid: message schema id
              else  { // If everything successful
                  if ("message" in res) {
                      var message = res["message"];
                      if( watched_message.indexOf( res['message_schemaid'] ) == -1 ) {
                          $("#message-parameter-table").append( res['message_row'] );
                          
                          watched_message.push( res['message_schemaid'] );
                      }
                  }
              }
              
              // show_loader(false);
          }
          else if (!res['uid']) {
              
          }
          else {
              notify(res, false);
          }

          setTimeout(fetch_watch_message, 1 * 1000); // 1 second
      }
  ).fail(function(res) {
      alert("Please refresh the page!");
  });
}

class RuleSelector extends React.Component {
  constructor(props) {
    super(props);
    this.state  = {
        rules: [],
        selected_rule_id: null, 
        params: [],
        nextPageURL:  ''
    };
  }

  applyRule(e, er_id) {
    show_loader(true);
    // Get selected messages
    $.each($("input[name='watched_message']:checked"), function(k, v) {
      var kargs = {};
      $(e.target).parent().parent().find('input').each(function(index, elem) {
          kargs[$(elem).attr("name")] = $(elem).val();
      })
  
      var params = {
        "er_id": er_id,
        "msg_id": parseInt($(v).parents('tr').attr("message-index")),
        "kargs": JSON.stringify(kargs)
      };
  
      console.log(params)
      
      $.post('/apply_button_rule', params,
          function(res) {
              console.log(res);
  
              if (res.status) {
                  notify(res, true);
              }
              else {
                  notify(res, false);
              }
  
              show_loader(false);
          }
      ).fail(function(res) {
          alert("Please refresh the page!");
      });
    })
  }

  handleSelect(e, er_id) {
    $("#rule-selector-table tr").css("opacity", 0.5)
    $("[er-id=" + er_id + "]").parents("tr").css("opacity", 1)
    $(".rule-select-btn").text("Select")
    $(".rule-select-btn[er-id=" + er_id + "]").html('<i class="fas fa-check"></i>')

    // Remove and Load new parameters table
    ReactDOM.unmountComponentAtNode(document.getElementById('message-param-container'))

    var params = [];
    $.each(this.state.rules, function(k, rule) {
      if (rule['id'] == er_id) {
        params = rule['params'];
      }
    })

    ReactDOM.render(
      <MessageParameter selected_rule_id={er_id} params={params}/>,
      document.getElementById('message-param-container')
    );
  }

  componentDidMount() {
    buttonService.getRules().then(results => {
      console.log(results)
      this.setState({ rules: results.rules});

      show_loader(false);
    });
  }

  render() {
    return (
      <table class="table table-striped" id="rule-selector-table">
        <tbody>
              {this.state.rules.map( er  =>
                <tr>
                  <td>{ er.name } &lt;<a href={["mailto:", er.email, "?Subject=YouPS%20"].join()} target="_top">{ er.email }</a>&gt; </td>
                  <td>
                    <ul>
                      {er.params.map( param  => <li>{ param.name }: <span dangerouslySetInnerHTML={{__html: param.html}}></span></li>)}
                    </ul>
                  </td>
                  <td><button className='btn btn-info rule-select-btn' er-id={er.id} onClick={(e)=>  this.applyRule(e, er.id) }>Apply</button></td>
                </tr>
              )}
        </tbody>
      </table>
    );
  }
}

function show_loader( is_show ) {
  if(is_show) $(".sk-circle").show();
  else $(".sk-circle").hide();
}

$(document).ready(function() {
  fetch_watch_message();

  ReactDOM.render(
    <RuleSelector/>,
    document.getElementById('rule-container')
  );

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

  if(is_authenticated) 
    fetch_log();
})