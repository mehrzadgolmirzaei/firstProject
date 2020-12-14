import React, { useEffect, useState } from "react";
import { withRouter } from "react-router";
import "bootstrap/dist/css/bootstrap.min.css";

const CardId = ({ history }) => {
  const [users, setUsers] = useState([]);
  const [forceUpdate, setForceUpdate] = useState(false);





//   const gotoinfo = (user) => {
    
// setShowUser(user);

//     history.push("/userinfo");
//   };





  const handleDeleteUser = (user) => {
    let all = JSON.parse(localStorage.getItem("users"));
    all = all.filter((tt) => tt.id !== user.id);
    localStorage.setItem("users", JSON.stringify(all));
    setForceUpdate(!forceUpdate);
  };

  useEffect(() => {
    setUsers(JSON.parse(localStorage.getItem("users")));
  }, [forceUpdate]);

  return (
    <div className="container">
      <section className="card mb-5">
        <div className="card-body">
          <h1 className="alert-dark text-light text-center">ID NUMBER</h1>
          <hr />

          {users.map((user) => (
            <div key={user.id}>
              <h3 className="text-center card-title text-primary alert alert-success">
                Card ID
              </h3>
              <h4 className=" card-text">
                lastname
                <p className="   font-weight-light bg-light">
                  {user.firstname}
                </p>
              </h4>
              <br />
              <h4 className=" card-text">
                firstname{" "}
                <p className="   font-weight-light  bg-light">
                  {user.lastname}
                </p>{" "}
              </h4>
              <br />
              <h4 className=" card-text">
                {" "}
                age<p className="   font-weight-light">{user.age} </p>
              </h4>
              <button
                // onClick={() => gotoinfo(user)}
                className="btn   btn-info  btn-block "
              >
                نمایش اشخاص
              </button>
              <button
                className="btn   btn-warning  btn-block "
                onClick={() => handleDeleteUser(user)}
              >
                {" "}
                حذف
              </button>
              <hr />
            </div>
          ))}

          <hr />
          <button
            onClick={() => history.push("/editid")}
            className="btn btn-primary "
          >
            ثبت/ویرایش
          </button>
          <button
            onClick={() => history.push("/listdoros")}
            className="btn btn-danger float-right"
          >
            لیست دروس
          </button>
        </div>
      </section>
    </div>
  );
};

export default withRouter(CardId);
