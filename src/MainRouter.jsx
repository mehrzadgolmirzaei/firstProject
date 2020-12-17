import React from "react";
import { Route, Switch } from "react-router";
import CardId from "./CardId";
import { useState } from "react";
import EditID from "./EditID";
import ListDoros from "./ListDoros";
import Login from "./Login";
import Userinfo from "./Userinfo";


const MainRouter = () => {
  const [users, setusers] = useState([]);

  const [showuser, setShowuser] = useState();

  return (
    <Switch>
      <Route path="/login" exact render={() => <Login/> } />
      <Route
        path="/cardid"
        render={() => <CardId users={users} setusers={setusers} setShowuser={setShowuser} />}
      />
      <Route
        path="/editid"
        render={() => <EditID setusers={setusers} users={users} />}
      />
      <Route path="/listdoros" render={() => <ListDoros />} />
      <Route path="/userinfo/:id" render={(props) => <Userinfo userId={props.match.params.id} showuser={showuser} />} />
      
    </Switch>
  );
};

export default MainRouter;
