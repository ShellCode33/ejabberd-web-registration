# ejabberd-web-registration
Simple Jabber registration using Python 3.

This application will enable you to control users accessing your XMPP server. You may want to create a private messaging server, unfortunatly you can't because registration is open or has to be manual. Thanks to this, you'll be able to accept or deny registrations easily. This application is secured by design and never stores any plaintext password (nor reversible).

The webserver has to run with the ejabberd user in order to be able to use the ejabberdctl program which performs registration.
In order to do so, the sudo command will be used.

Your ejabberd installation has to use a MySQL database to run this application. (Can also be a MySQL-compatible DBMS such as MariaDB)

## Dependencies
First install the MySQL connector (MariaDB fork in this case). This is a debian installation using apt, but you can also install the appropriate package depending on your distribution.
```
sudo apt install python3-mysqldb libmariadbclient-dev #libmysqlclient-dev package for standard MySQL database
```

Python3 will need a few libraries to run this code
```
sudo -u ejabberd pip3 install flask
sudo -u ejabberd pip3 install flask_recaptcha
sudo -u ejabberd pip3 install flask-mysqldb
```

## Prepare database
You will have to create a table in order to store the users waiting for approval.
To do so, please execute the following statement :
```
CREATE TABLE users_waiting_approval (username VARCHAR(100) NOT NULL PRIMARY KEY, password VARCHAR(128) NOT NULL, email VARCHAR(200));
```

## File permission
The file `config.py` has to be owned by ejabberd because the application will overwrite this file.
Please execute :
```
sudo chown ejabberd:ejabberd config.py
```

## Running
This is as simple as :
```
sudo -u ejabberd ./main.py
```
You can also run it in background like this :
```
sudo -u ejabberd nohup ./main.py &
```
