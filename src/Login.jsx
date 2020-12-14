import React, { useEffect } from "react";
import { useState } from "react";
import { withRouter } from "react-router";

const Login = ({ history }) => {
  const [username, setUsername] = useState();
  const [password, setPassword] = useState();

  const handleLogin = (event) => {
    event.preventDefault();
    if (username === "0912" && password === "123") {
      history.push("/cardid");
    }
  };

  useEffect(() => {
    localStorage.setItem("users", "[]");
  }, []);

  return (
    <div
      className="text-center mx-auto logincard bg-light "
      style={{ maxWidth: "500px" }}
    >
      <form className="card p-2 mt-5" onSubmit={(e) => handleLogin(e)}>
        <div className="form-group">
          <label for="exampleInputEmail1">نام کاربری </label>
          <input
            type="text"
            className="form-control"
            aria-describedby="emailHelp"
            onChange={(e) => setUsername(e.target.value)}
          />
        </div>
        <div className="form-group">
          <label>رمز عبور</label>
          <input
            type="password"
            className="form-control"
            id="exampleInputPassword1"
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>

        <button type="submit" className="btn btn-primary">
          Submit
        </button>
      </form>
    </div>
  );
};

export default withRouter(Login);
