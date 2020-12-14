import userEvent from "@testing-library/user-event";
import React from "react";
import { withRouter } from "react-router";

const Userinfo = ({  showUser, history  }) => {
  return (
    <div>
      <h1
        className="text-center text-danger"
        onClick={() => history.push("/cardid")}
      >
      
        {/* {`${showUser.firstname} ${showUser.lastname} ${showUser.age}`}
     */}
      </h1>
    </div>
  );
};

export default withRouter(Userinfo);
