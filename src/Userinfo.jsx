import React, { useEffect, useState } from "react";
import { withRouter } from "react-router";

const Userinfo = ({ history, userId }) => {
  const [selectedUser, setSelectedUser] = useState();

  useEffect(() => {
    let user = JSON.parse(localStorage.getItem("users")).find(
      (t) => t.id == userId
    );
    setSelectedUser(user);
  }, []);

  return (
    <div>
      <h1
        className="text-center text-danger"
        onClick={() => history.push("/cardid")}
        
      >
        
        {selectedUser
          ? `${selectedUser.firstname} ${selectedUser.lastname} ${selectedUser.age}`
          : ""}
      </h1>
    </div>
  );
};

export default withRouter(Userinfo);
