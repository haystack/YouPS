const API_URL = 'http://localhost:8000';

class ButtonService extends React.Component {

    constructor(props){
        super(props);
    }

    getRules() {
        const url = '/email_rule_meta';
        return axios.get(url, {withCredentials: true}).then(response => response.data);
    }  
    getUpcomingEvents() {
        const url = '/fetch_upcoming_events';
        return axios.get(url, {withCredentials: true}).then(response => response.data);
    }  
    getCustomer(pk) {
        const url = `/fetch_watch_message`;
        return axios.post(url).then(response => response.data);
    }
    deleteCustomer(customer){
        const url = `${API_URL}/api/customers/${customer.pk}`;
        return axios.delete(url);
    }
    createCustomer(customer){
        const url = `${API_URL}/api/customers/`;
        return axios.post(url,customer);
    }
    updateCustomer(customer){
        const url = `${API_URL}/api/customers/${customer.pk}`;
        return axios.put(url,customer);
    }
}