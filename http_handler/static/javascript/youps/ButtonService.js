const API_URL = 'http://localhost:8000';

class ButtonService extends React.Component {

    constructor(props){
        super(props);
    }

    getRules() {
        const url = '/email_rule_meta';
        return axios.get(url, {withCredentials: true}).then(response => response.data);
    }  
    getCustomersByURL(link){
        const url = `${API_URL}${link}`;
        return axios.get(url).then(response => response.data);
    }
    getCustomer(pk) {
        const url = `${API_URL}/api/customers/${pk}`;
        return axios.get(url).then(response => response.data);
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