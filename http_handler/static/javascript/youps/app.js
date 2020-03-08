const  buttonService  =  new ButtonService();


class DatePicker extends React.Component {
  constructor(props) {
    super(props);
    this.state  = {
        schedule: []
    };
    this.dateCustom = React.createRef();
    this.a = ""
    this.b = Math.random().toString(36).substring(7)

    var day = new Date();
    this.today_val = day.getFullYear() + "-" + (day.getMonth() +1).toString().padStart(2, 0) + "-" + day.getDate().toString().padStart(2, 0) + " 13:00"
    var nextDay = new Date(day);
    nextDay.setDate(day.getDate() + 1);
    this.d_val = nextDay.getFullYear() + "-" + (nextDay.getMonth() +1).toString().padStart(2, 0) + "-" + nextDay.getDate().toString().padStart(2, 0) + " 13:00"
  }

  handleSelect(e) {
    if (e.tagName != "A") e = e.parentElement
    $(e).parents('.dropdown').find('input.dropdown-toggle')
      .val($(e).data('value'));
  }

  showDatePicker(e) {
    this.a.show();
    e.stopPropagation();
  }

  componentDidUpdate() {
    // respond to the 
  }

  componentDidMount() {
    var self = this;
    $("input[name='"+ this.props.name +"']").val(this.d_val);
    this.a = new Pikaday(
      {
          field: document.getElementById(this.b),//self.dateCustom.current,
          format : "Select a date",
          firstDay: 1,
          minDate: new Date(),
          maxDate: new Date('2025-01-01'),
          yearRange: [2020,2025],
          onSelect: function(date) {
            // field.value = picker.toString();
            console.log(date)
            const day = date.getDate();
            const month = date.getMonth() + 1;
            const year = date.getFullYear();
            // $(this._o.field).parents(".dropdown").find('input.dropdown-toggle').html(`${year} ${month}/${day} 13:00` + ' <span class="caret"></span>');
            $(this._o.field).parents(".dropdown").find('input.dropdown-toggle').val(`${year}-${month}-${day} 13:00`);
          }
      });

    // Prevent custom date selector to be closed
    $(document).on('click', '.dropdown-menu .dropdown-toggle-skip', function (e) {
        e.stopPropagation();
    });

    buttonService.getUpcomingEvents().then(results => {
      console.log(results)
      self.setState({ schedule: results.events});
      
    });
  }

  render() {
    var date_style = {color: "grey"};

    
    return (
      <div class="row">
      <div class="input-group dropdown">
          <input name={this.props.name} type="text" class="form-control dropdown-toggle" data-toggle="dropdown" data-value={this.d_val} />
          <ul class="dropdown-menu">
            <li><a onClick={(e)=>  this.handleSelect(e.target) } data-value={this.d_val}>tomorrow</a></li>
            {this.state.schedule.map( er  =>
              <li><a onClick={(e)=>  this.handleSelect(e.target) } data-value={er.start_text}>{er.name} 
                <span style={date_style}> {this.today_val.slice(0, 10) == er.start_text.slice(0, 10) ? er.start_text.slice(11):er.start_text} ~ {this.today_val.slice(0, 10) == er.end_text.slice(0, 10) ? er.end_text.slice(11):er.end_text}</span></a></li>
            )}
             <li class='dropdown-toggle-skip'><a onClick={(e)=>  this.showDatePicker(e) } data-value={this.d_val}><input class="skip" ref={this.dateCustom} id={this.b} value='Select a date'/></a></li>
          </ul>
          <span role="button" class="input-group-addon dropdown-toggle" data-toggle="dropdown" aria-haspopup="true" aria-expanded="false"><span class="caret"></span></span>
        
        </div></div>
    );
  }
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
    debugger;

    if($("input[name='watched_message']:checked").length == 0) {
      show_loader(false);
      alert("You should select a message!");
      return;
    }
    
    // Get selected messages
    $.each($("input[name='watched_message']:checked"), function(k, v) {
      var kargs = {};
      $(e.target).parent().parent().find('input').each(function(index, elem) {
          if(!$(elem).attr("name")) return;
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

  removeOnresponse(e) {
    var params = {"msg_id": $("input[name='watched_message']:checked").parents('tr').attr("message-index")};

    $.post('/remove_on_response_event', params,
    function(res) {
        console.log(res);
        
        // Create success
        if (res.status) {
            console.log("remove success");
            $("input[name='watched_message']:checked").parents('tbody').removeAttr('on_response');
            res['code'] = "on_response() event has been removed";
            notify(res, true);
        }
        else {
            notify(res, false);
        }
    });
  }

  removeOntime(e) {
    var params = {"msg_id": $("input[name='watched_message']:checked").parents('tr').attr("message-index")};

    $.post('/remove_on_time_event', params,
    function(res) {
        console.log(res);
        
        // Create success
        if (res.status) {
            console.log("remove success");
            $("input[name='watched_message']:checked").parents('tbody').removeAttr('on_time');
            res['code'] = "on_time() event has been removed";
            notify(res, true);
        }
        else {
            notify(res, false);
        }
    });
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

      $('[data-toggle="tooltip"]').tooltip();

      show_loader(false);
    });

    
  }

  

  render() {
    var table_style = {background: "aliceblue", width:"100%"};
    var hide_style = {display: "none"};
    var row_style={"margin-top": "10px", "padding-bottom": "5px", "border-bottom": "1px solid"}
    return (
      <div class="container" style={table_style} id="rule-selector-table">
        <div class="row on-response-rule" style={Object.assign({}, hide_style, row_style)} >
          <div class="col-md-9">
              Remove <code>on_response()</code> event from this thread<span data-toggle="tooltip" data-placement="bottom" data-html="true" title="current on_response() event won't be triggered from now on" class="glyphicon glyphicon-info-sign"></span>
            </div>
            <div class="col-md-2">
                <ul>
                </ul>
            </div>
            <div class="col-md-1">
                <button className='btn btn-info rule-select-btn' onClick={(e)=>  this.removeOnresponse(e) }>Run</button>
          </div>
        </div>
        <div class="row on-time-rule" style={Object.assign({}, hide_style, row_style)}>
          <div class="col-md-9">
              Remove <code>on_time()</code> event from this message<span data-toggle="tooltip" data-placement="bottom" data-html="true" title="current on_time() event won't be triggered from now on" class="glyphicon glyphicon-info-sign"></span>
            </div>
            <div class="col-md-2">
                <ul>
                </ul>
            </div>
            <div class="col-md-1">
                <button className='btn btn-info rule-select-btn' onClick={(e)=>  this.removeOntime(e) }>Run</button>
          </div>
        </div>
        {this.state.rules.map( er  =>
          <div class="row" style={row_style}>
            <div class="col-md-9">
            { er.name }<span data-toggle="tooltip" data-placement="bottom" data-html="true" title={["<div style='position:relative;overflow:auto;'><p>" + er.code.replace(/ /gi, '&nbsp;').replace("\t", "&nbsp;&nbsp;&nbsp;&nbsp;").replace(/\n/g, "<br>") + "</p></div>"].join()} class="glyphicon glyphicon-info-sign"></span> 
              {
                er.params.length <= 1 &&
                  <span>&lt;<a href={["mailto:", er.email, "?Subject=YouPS%20"].join()} target="_top">{ er.email }</a>&gt;</span>
              } 
            </div>
            <div class="col-md-2">
              <ul>
                {er.params.map( param  => <li>{ param.name }: {param.type=="datetime"? 
                  <DatePicker name={ param.name }/>:<span dangerouslySetInnerHTML={{__html: param.html}}></span>} </li>)}
              </ul>
            </div>
            <div class="col-md-1">
              <button className='btn btn-info rule-select-btn' er-id={er.id} onClick={(e)=>  this.applyRule(e, er.id) }>Run</button>
            </div>
            </div>)}
      </div>
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

  // TODO as go to different tools 
  $(".message-parameter-table").on('change', 'input', function() {
    // change children's value
    $(".on-response-rule").hide();
    $(".on-time-rule").hide();

    if($(this).parents('tbody').attr('on_response'))
      $(".on-response-rule").show();

    if($(this).parents('tbody').attr('on_time'))
      $(".on-time-rule").show();
  });
  

  if(is_authenticated) 
    fetch_log();
})